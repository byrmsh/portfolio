---
title: 'Pulumi K3s Guide'
description: 'Guide for running a Zero-Trust Kubernetes node on Hetzner with Cloudflare Tunnel and Pulumi with no open inbound ports'
pubDate: '11 Jan 2026'
heroImage: '../../assets/blog-placeholder-3.jpg'
---

### Introduction

When running infrastructure on the public internet, the default approach has historically been to expose services and then defend them: firewalls, SSH hardening, IP allowlists, VPNs, bastion hosts, and so on. Even when done well, this still leaves an attack surface that is permanently visible.

In this guide, we take a different approach. We build a **single-node K3s control plane on Hetzner Cloud** that:

- Has **no open inbound ports**
- Does **not expose SSH or the Kubernetes API publicly**
- Uses **Cloudflare Tunnel** as the only ingress mechanism
- Is provisioned end-to-end using **Pulumi (TypeScript)**

The server initiates all connections outbound, Cloudflare brokers access at the edge, and identity replaces network location as the security boundary.

### High-Level Shape of the Setup

At the end of the guide:

- The Hetzner VM runs `cloudflared`, SSH, K3s, and HTTP services bound to localhost
- Cloudflare Tunnel forwards traffic to those local services based on hostname
- DNS points at the tunnel, not at the VMs IP
- Hetzner firewall allows nothing inbound
- UFW on the VM also denies all incoming traffic

The VM technically has a public IP, but it is never used for ingress.

### Prerequisites

**Accounts:** We need a **Cloudflare account** with a domain already added and a **Hetzner Cloud account**.

**Local Tools:** Installed locally you should have Node.js 18+, the Pulumi CLI, `cloudflared`, `kubectl`, and `ssh`.

### CF: One-Time Web UI Preparation

**Enabling Zero Trust:** In the Cloudflare dashboard, go to **Zero Trust**, choose a team name, and enable the (free) plan; this unlocks Cloudflare Tunnel and Access features for the account.

**Creating a Cloudflare API Token:** Pulumi will manage tunnels and DNS on our behalf, so create a token in **My Profile API Tokens** as a **Custom Token** scoped to the account and domain with the following permissions: Account Cloudflare Tunnel Edit, Account Access: Apps and Policies Edit, and Zone DNS Edit. Store the token securely.

**Collecting IDs:** From the Cloudflare dashboard note the **Account ID** and the **Zone ID** for the domain; these will be used in Pulumi configuration.

### Hetzner: One-Time Setup

API Token:

API Token: In the Hetzner Cloud Console, under **Security API Tokens**, create a token with read/write access.

SSH Key:

SSH Key: If you don't already have a key you want to use, create one (for example `ssh-keygen -t ed25519 -C "hetzner-zero-trust"`) and Pulumi will reference the public key.

### Pulumi Project Initialization

We create a new Pulumi TypeScript project and install the providers:

```bash
pulumi new typescript
npm install @pulumi/hcloud @pulumi/cloudflare @pulumi/random
```

Then we configure the stack:

```bash
pulumi config set cloudflareAccountId <ACCOUNT_ID>
pulumi config set cloudflareZoneId <ZONE_ID>
pulumi config set domainName example.com
pulumi config set sshPublicKey "$(cat ~/.ssh/id_ed25519.pub)"

pulumi config set cloudflare:apiToken <CF_API_TOKEN> --secret
pulumi config set hcloud:token <HETZNER_TOKEN> --secret
```

### Creating the Cloudflare Tunnel

We start by defining the tunnel itself and generating a secret for it. This represents the tunnel identity inside Cloudflare.

```ts
const tunnelSecret = new random.RandomId('tunnel-secret', {
  byteLength: 32,
}).b64Std;

export const tunnel = new cloudflare.ZeroTrustTunnelCloudflared('k8s-tunnel', {
  accountId: cfAccountId,
  name: 'hetzner-platform',
  tunnelSecret: tunnelSecret,
});
```

Cloudflare expects the tunnel daemon to authenticate using a base64-encoded token. Pulumi does not expose this directly, so we construct it ourselves:

```ts
const tunnelToken = pulumi.all([tunnel.id, tunnelSecret]).apply(([id, secret]) => {
  const json = JSON.stringify({ a: cfAccountId, t: id, s: secret });
  return Buffer.from(json).toString('base64');
});
```

This token will later be injected into the server during first boot.

### Defining Tunnel Ingress Rules

With the tunnel created, we tell Cloudflare how incoming hostnames should be routed to local services on the VM.

```ts
export const tunnelConfig = new cloudflare.ZeroTrustTunnelCloudflaredConfig('k8s-tunnel-config', {
  accountId: cfAccountId,
  tunnelId: tunnel.id,
  config: {
    ingresses: [
      {
        hostname: `ssh.${domainName}`,
        service: 'ssh://localhost:22',
      },
      {
        hostname: `k8s.${domainName}`,
        service: 'tcp://localhost:6443',
      },
      {
        hostname: `*.${domainName}`,
        service: 'http://localhost:80',
      },
      {
        hostname: domainName,
        service: 'http://localhost:80',
      },
      { service: 'http_status:404' },
    ],
  },
});
```

This gives us:

- SSH access via a hostname
- Remote `kubectl` access without exposing the API
- A clean path for HTTP workloads later

### DNS Records Pointing at the Tunnel

Now that the tunnel exists and knows how to route traffic, we add DNS records that point to it.

```ts
const createRecord = (name: string, recordName: string) =>
  new cloudflare.DnsRecord(name, {
    zoneId: cfZoneId,
    name: recordName,
    content: pulumi.interpolate`${tunnel.id}.cfargotunnel.com`,
    type: 'CNAME',
    proxied: true,
    ttl: 1,
  });

export const dnsSsh = createRecord('dns-ssh', 'ssh');
export const dnsK8s = createRecord('dns-k8s', 'k8s');
export const dnsWildcard = createRecord('dns-wildcard', '*');
export const dnsApex = createRecord('dns-apex', '@');
```

At no point do these records reference the Hetzner servers IP. All traffic terminates at Cloudflare first.

### Provisioning the Hetzner Server

On the Hetzner side, we create:

- An SSH key resource
- A firewall with **no inbound rules**
- A server with a cloud-init script that bootstraps everything

```ts
const mainKey = new hcloud.SshKey('main-key', {
  publicKey: sshPublicKey,
});

const firewall = new hcloud.Firewall('lockdown', { rules: [] });
```

The cloud-init configuration installs `cloudflared`, registers the tunnel, locks down the OS firewall, and installs K3s:

```ts
const cloudInit = tunnelToken.apply(
  (token) => `#cloud-config
package_update: true
package_upgrade: true
packages:
  - curl
  - git
  - ufw

runcmd:
  - curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
  - dpkg -i cloudflared.deb
  - cloudflared service install ${token}

  - ufw default deny incoming
  - ufw default allow outgoing
  - ufw enable

  - curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --tls-san k8s.${domainName}" sh -
`,
);
```

Finally, the server itself:

```ts
const node = new hcloud.Server('platform-node', {
  serverType: 'cax21',
  image: 'ubuntu-24.04',
  location: 'nbg1',
  sshKeys: [mainKey.id],
  firewallIds: [firewall.id.apply((id) => parseInt(id, 10))],
  userData: cloudInit,
  publicNets: [{ ipv4Enabled: true, ipv6Enabled: true }],
  labels: { role: 'control-plane' },
});

export const ip = node.ipv4Address;
export const k8sApiEndpoint = `https://k8s.${domainName}:6443`;
```

### Deploying Everything

```bash
pulumi up
```

After a few minutes, the tunnel is connected, the node is ready, and Kubernetes is running without exposing a single port.

### Client-Side Access: cloudflared Login

Before using SSH or `kubectl`, we authenticate our local machine with Cloudflare:

```bash
cloudflared login
```

This associates the client with our Cloudflare account.

### SSH via Cloudflare Tunnel

```bash
cloudflared access ssh --hostname ssh.example.com
ssh user@ssh.example.com
```

### Local Systemd Service for Kube API

Instead of manually running `cloudflared access tcp` every time, we can keep the tunnel up using a user-level systemd service.

```ini
[Unit]
Description=Cloudflared Access Bash K8s
After=network.target

[Service]
ExecStart=cloudflared access tcp --hostname k8s.example.com --listener 127.0.0.1:6443
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

Enable it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now cloudflared-bash-k8s.service
```

Now the Kubernetes API is always available locally on `127.0.0.1:6443`.

### Kubernetes Config

On the server:

```bash
sudo cat /etc/rancher/k3s/k3s.yaml
```

We replace the server address with:

```
https://127.0.0.1:6443
```

Then locally:

```bash
kubectl get nodes
```

### Conclusion

In this guide, we built a zero-trust K3s control plane on Hetzner Cloud using Pulumi and Cloudflare Tunnel. The server has no open inbound ports, and all access is brokered securely through Cloudflare, demonstrating a modern approach to infrastructure security.

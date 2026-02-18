import { getCollection } from 'astro:content';

export type NodeType = 'hub' | 'project' | 'blog' | 'tag';

export interface GraphNode {
  id: string;
  label: string;
  type: NodeType;
  href?: string;
}

export interface GraphLink {
  source: string;
  target: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export async function buildGraphData(locale = 'eng'): Promise<GraphData> {
  const prefix = locale !== 'eng' ? `/${locale}` : '';

  const [blogs, projects] = await Promise.all([getCollection('blog'), getCollection('projects')]);

  const nodes: GraphNode[] = [];
  const links: GraphLink[] = [];
  const tagSet = new Set<string>();

  // Hub nodes
  nodes.push({ id: 'hub:projects', label: 'Projects', type: 'hub', href: `${prefix}/projects` });
  nodes.push({ id: 'hub:blogs', label: 'Blog', type: 'hub', href: `${prefix}/blog` });

  // Project nodes
  for (const project of projects.filter((p) => !p.data.draft)) {
    const nodeId = `project:${project.slug}`;
    nodes.push({
      id: nodeId,
      label: project.data.title,
      type: 'project',
      href: `${prefix}/projects/${project.slug}`,
    });
    links.push({ source: nodeId, target: 'hub:projects' });

    // Stack tags
    for (const tech of project.data.stack) {
      const tagId = `tag:${tech}`;
      if (!tagSet.has(tagId)) {
        tagSet.add(tagId);
        nodes.push({ id: tagId, label: tech, type: 'tag' });
      }
      links.push({ source: nodeId, target: tagId });
    }
  }

  // Blog nodes
  for (const post of blogs.filter((p) => !p.data.draft)) {
    const nodeId = `blog:${post.slug}`;
    nodes.push({
      id: nodeId,
      label: post.data.title,
      type: 'blog',
      href: `${prefix}/blog/${post.slug}`,
    });
    links.push({ source: nodeId, target: 'hub:blogs' });

    // Blog tags
    for (const tag of post.data.tags ?? []) {
      const tagId = `tag:${tag}`;
      if (!tagSet.has(tagId)) {
        tagSet.add(tagId);
        nodes.push({ id: tagId, label: tag, type: 'tag' });
      }
      links.push({ source: nodeId, target: tagId });
    }
  }

  return { nodes, links };
}

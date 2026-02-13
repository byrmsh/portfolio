import { SITE as SITE_UNTYPED } from '../../site.config.mjs';

export const SITE = SITE_UNTYPED as Readonly<{ name: string; domain: string }>;

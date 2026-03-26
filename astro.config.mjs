import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://mitchross.github.io',
  base: '/talos-argocd-proxmox',
  integrations: [
    starlight({
      title: 'Talos ArgoCD Proxmox',
      description: 'Production-grade GitOps Kubernetes cluster on Talos OS — self-healing, GPU-enabled, fully automated',
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/mitchross/talos-argocd-proxmox' },
      ],
      customCss: ['./src/styles/custom.css'],
      editLink: {
        baseUrl: 'https://github.com/mitchross/talos-argocd-proxmox/edit/main/',
      },
      sidebar: [
        {
          label: 'Architecture',
          autogenerate: { directory: 'architecture' },
        },
        {
          label: 'Backup & DR',
          autogenerate: { directory: 'backup' },
        },
        {
          label: 'Design Docs',
          autogenerate: { directory: 'designs' },
        },
      ],
    }),
  ],
});

import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

const sidebars: SidebarsConfig = {
  tutorialSidebar: [
    'overview',
    'getting-started',
    'concepts',
    'cli',
    {
      type: 'category',
      label: 'API',
      items: ['api/python', 'api/batch', 'api/service'],
    },
    {
      type: 'category',
      label: 'Agent Skills / MCP',
      items: ['skills/overview', 'skills/skills', 'skills/mcp-server', 'skills/mcp-shrink'],
    },
    {
      type: 'category',
      label: 'Examples',
      items: ['examples/developer', 'examples/agent'],
    },
    'stats',
    'faq',
  ],
};

export default sidebars;

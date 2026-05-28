import type {ReactNode} from 'react';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import CompressionShowcase from '../components/CompressionShowcase/CompressionShowcase';

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title={siteConfig.title}
      description="Token-level context compression for LLM and agent workflows.">
      <CompressionShowcase />
    </Layout>
  );
}

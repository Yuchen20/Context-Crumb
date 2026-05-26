import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import bannerUrl from '@site/assets/contextcrumb-banner.png';

import styles from './index.module.css';

function HomepageHeader() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <div className={styles.buttons}>
          <Link
            className="button button--secondary button--lg"
            to="/docs/overview">
            Read the docs
          </Link>
          <Link
            className="button button--outline button--secondary button--lg"
            to="https://huggingface.co/spaces/ymao20/contextcrumb-32m-demo">
            Open playground
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title={siteConfig.title}
      description="Token-level context compression for LLM and agent workflows.">
      <HomepageHeader />
      <main>
        <section className={styles.bannerSection}>
          <div className="container">
            <img
              className={styles.bannerImage}
              src={bannerUrl}
              alt="ContextCrumb banner"
            />
          </div>
        </section>
      </main>
    </Layout>
  );
}

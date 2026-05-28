import type {ReactNode} from 'react';
import type {BufferAttribute, MeshBasicMaterial} from 'three';
import BrowserOnly from '@docusaurus/BrowserOnly';
import Link from '@docusaurus/Link';
import clsx from 'clsx';
import {Fragment, useEffect, useMemo, useRef, useState} from 'react';

import styles from './CompressionShowcase.module.css';

type DemoToken = {
  text: string;
  keepScore: number;
  keep: boolean;
  role: 'signal' | 'filler' | 'structure';
};

const DEMO_TOKENS: DemoToken[] = [
  {text: 'Agents', keepScore: 0.94, keep: true, role: 'signal'},
  {text: 'spend', keepScore: 0.78, keep: true, role: 'signal'},
  {text: 'context', keepScore: 0.96, keep: true, role: 'signal'},
  {text: 'on', keepScore: 0.24, keep: false, role: 'filler'},
  {text: 'notes,', keepScore: 0.89, keep: true, role: 'signal'},
  {text: 'logs,', keepScore: 0.86, keep: true, role: 'signal'},
  {text: 'tickets,', keepScore: 0.82, keep: true, role: 'signal'},
  {text: 'docs,', keepScore: 0.88, keep: true, role: 'signal'},
  {text: 'and', keepScore: 0.21, keep: false, role: 'filler'},
  {text: 'tool', keepScore: 0.91, keep: true, role: 'signal'},
  {text: 'descriptions.', keepScore: 0.9, keep: true, role: 'signal'},
  {text: 'Those', keepScore: 0.35, keep: false, role: 'structure'},
  {text: 'files', keepScore: 0.74, keep: true, role: 'signal'},
  {text: 'contain', keepScore: 0.62, keep: true, role: 'structure'},
  {text: 'useful', keepScore: 0.93, keep: true, role: 'signal'},
  {text: 'facts,', keepScore: 0.91, keep: true, role: 'signal'},
  {text: 'but', keepScore: 0.28, keep: false, role: 'filler'},
  {text: 'they', keepScore: 0.2, keep: false, role: 'filler'},
  {text: 'also', keepScore: 0.26, keep: false, role: 'filler'},
  {text: 'carry', keepScore: 0.56, keep: true, role: 'structure'},
  {text: 'filler', keepScore: 0.48, keep: false, role: 'filler'},
  {text: 'phrases', keepScore: 0.52, keep: true, role: 'structure'},
  {text: 'and', keepScore: 0.18, keep: false, role: 'filler'},
  {text: 'repeated', keepScore: 0.5, keep: true, role: 'structure'},
  {text: 'wording.', keepScore: 0.47, keep: false, role: 'filler'},
  {text: 'ContextCrumb', keepScore: 0.99, keep: true, role: 'signal'},
  {text: 'scores', keepScore: 0.87, keep: true, role: 'signal'},
  {text: 'each', keepScore: 0.4, keep: false, role: 'structure'},
  {text: 'token,', keepScore: 0.96, keep: true, role: 'signal'},
  {text: 'keeps', keepScore: 0.92, keep: true, role: 'signal'},
  {text: 'the', keepScore: 0.23, keep: false, role: 'filler'},
  {text: 'original', keepScore: 0.93, keep: true, role: 'signal'},
  {text: 'order,', keepScore: 0.91, keep: true, role: 'signal'},
  {text: 'and', keepScore: 0.19, keep: false, role: 'filler'},
  {text: 'removes', keepScore: 0.89, keep: true, role: 'signal'},
  {text: 'low-value', keepScore: 0.85, keep: true, role: 'signal'},
  {text: 'padding.', keepScore: 0.83, keep: true, role: 'signal'},
];

const TIMELINE_SECONDS = 9;

function clamp(value: number, min = 0, max = 1): number {
  return Math.min(max, Math.max(min, value));
}

function smoothstep(edge0: number, edge1: number, value: number): number {
  const x = clamp((value - edge0) / (edge1 - edge0));
  return x * x * (3 - 2 * x);
}

function useReducedMotion(): boolean {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReducedMotion(query.matches);
    update();
    query.addEventListener('change', update);
    return () => query.removeEventListener('change', update);
  }, []);

  return reducedMotion;
}

function CompressionScene({
  progressRef,
  reducedMotion,
}: {
  progressRef: React.MutableRefObject<number>;
  reducedMotion: boolean;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let disposed = false;
    let frameId = 0;
    let isVisible = true;
    let isTabVisible = document.visibilityState === 'visible';
    const mountElement = mountRef.current;

    if (!mountElement) {
      return undefined;
    }

    async function runScene(sceneMount: HTMLDivElement) {
      const THREE = await import('three');

      if (disposed || !mountRef.current) {
        return;
      }

      const scene = new THREE.Scene();
      scene.fog = new THREE.FogExp2(0x07080d, 0.035);

      const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 120);
      camera.position.set(0, 7.5, 14);
      camera.lookAt(0, 0, 0);

      const renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: 'high-performance',
      });
      renderer.setClearColor(0x05060a, 0);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
      sceneMount.appendChild(renderer.domElement);

      const world = new THREE.Group();
      world.rotation.x = -0.54;
      world.rotation.z = 0.05;
      scene.add(world);

      const accentCyan = new THREE.Color(0x6de7ff);
      const accentAmber = new THREE.Color(0xff8b2f);
      const accentViolet = new THREE.Color(0xa58cff);
      const softWhite = new THREE.Color(0xe7ebff);

      function makeGrid(size: number, divisions: number, y: number, color: number, opacity: number) {
        const vertices: number[] = [];
        const half = size / 2;
        for (let i = 0; i <= divisions; i += 1) {
          const p = -half + (i / divisions) * size;
          vertices.push(-half, y, p, half, y, p);
          vertices.push(p, y, -half, p, y, half);
        }
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
        const material = new THREE.LineBasicMaterial({
          color,
          transparent: true,
          opacity,
          blending: THREE.AdditiveBlending,
        });
        return new THREE.LineSegments(geometry, material);
      }

      const lowerGrid = makeGrid(15, 30, -2.2, 0x355b64, 0.28);
      const upperGrid = makeGrid(12, 18, 2.1, 0xe8e9ff, 0.4);
      upperGrid.rotation.z = 0.09;
      world.add(lowerGrid, upperGrid);

      const heatGroup = new THREE.Group();
      const heatMaterials: MeshBasicMaterial[] = [];
      const cellGeometry = new THREE.PlaneGeometry(0.44, 0.44);
      const cellCount = 9;
      for (let x = 0; x < cellCount; x += 1) {
        for (let z = 0; z < cellCount; z += 1) {
          const intensity = Math.sin(x * 1.7) * Math.cos(z * 1.25) * 0.5 + 0.5;
          const material = new THREE.MeshBasicMaterial({
            color: intensity > 0.58 ? accentAmber : accentCyan,
            transparent: true,
            opacity: 0.08 + intensity * 0.12,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
          });
          const cell = new THREE.Mesh(cellGeometry, material);
          cell.position.set((x - 4) * 0.58, 2.12, (z - 4) * 0.58);
          cell.rotation.x = -Math.PI / 2;
          heatMaterials.push(material);
          heatGroup.add(cell);
        }
      }
      world.add(heatGroup);

      const pointCount = 260;
      const pointPositions = new Float32Array(pointCount * 3);
      const pointColors = new Float32Array(pointCount * 3);
      const pointSeeds: number[] = [];
      for (let i = 0; i < pointCount; i += 1) {
        const radius = 2 + Math.random() * 5.6;
        const angle = Math.random() * Math.PI * 2;
        pointPositions[i * 3] = Math.cos(angle) * radius;
        pointPositions[i * 3 + 1] = -1.9 + Math.random() * 3.8;
        pointPositions[i * 3 + 2] = Math.sin(angle) * radius;
        const color = i % 5 === 0 ? accentAmber : i % 3 === 0 ? accentViolet : accentCyan;
        pointColors[i * 3] = color.r;
        pointColors[i * 3 + 1] = color.g;
        pointColors[i * 3 + 2] = color.b;
        pointSeeds.push(Math.random() * Math.PI * 2);
      }
      const pointsGeometry = new THREE.BufferGeometry();
      pointsGeometry.setAttribute('position', new THREE.BufferAttribute(pointPositions, 3));
      pointsGeometry.setAttribute('color', new THREE.BufferAttribute(pointColors, 3));
      const pointsMaterial = new THREE.PointsMaterial({
        size: 0.06,
        vertexColors: true,
        transparent: true,
        opacity: 0.66,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const points = new THREE.Points(pointsGeometry, pointsMaterial);
      world.add(points);

      const strandsGeometry = new THREE.BufferGeometry();
      const strandVertices: number[] = [];
      for (let i = 0; i < 42; i += 1) {
        const angle = (i / 42) * Math.PI * 2;
        const inner = 1.2 + (i % 5) * 0.22;
        const outer = 5.2 + (i % 7) * 0.18;
        strandVertices.push(Math.cos(angle) * inner, -1.9, Math.sin(angle) * inner);
        strandVertices.push(Math.cos(angle + 0.2) * outer, 1.65, Math.sin(angle + 0.2) * outer);
      }
      strandsGeometry.setAttribute('position', new THREE.Float32BufferAttribute(strandVertices, 3));
      const strandsMaterial = new THREE.LineBasicMaterial({
        color: 0xff6a2a,
        transparent: true,
        opacity: 0.48,
        blending: THREE.AdditiveBlending,
      });
      const strands = new THREE.LineSegments(strandsGeometry, strandsMaterial);
      world.add(strands);

      const spikeGroup = new THREE.Group();
      const spikeGeometry = new THREE.BufferGeometry();
      spikeGeometry.setAttribute(
        'position',
        new THREE.Float32BufferAttribute([0, 0, 0, 0, 1, 0], 3),
      );
      for (let i = 0; i < 26; i += 1) {
        const score = DEMO_TOKENS[i % DEMO_TOKENS.length].keepScore;
        const material = new THREE.LineBasicMaterial({
          color: score > 0.7 ? softWhite : accentAmber,
          transparent: true,
          opacity: 0.45,
          blending: THREE.AdditiveBlending,
        });
        const spike = new THREE.Line(spikeGeometry, material);
        const angle = (i / 26) * Math.PI * 2;
        const radius = 1.2 + score * 3.2;
        spike.position.set(Math.cos(angle) * radius, -2.18, Math.sin(angle) * radius);
        spike.scale.y = 0.5 + score * 3.8;
        spikeGroup.add(spike);
      }
      world.add(spikeGroup);

      const resize = () => {
        if (!mountRef.current) {
          return;
        }
        const {clientWidth, clientHeight} = mountRef.current;
        renderer.setSize(clientWidth, clientHeight, false);
        camera.aspect = clientWidth / Math.max(clientHeight, 1);
        camera.updateProjectionMatrix();
      };

      const observer = new IntersectionObserver(
        ([entry]) => {
          isVisible = entry.isIntersecting;
        },
        {threshold: 0.05},
      );
      observer.observe(sceneMount);

      const onVisibilityChange = () => {
        isTabVisible = document.visibilityState === 'visible';
      };

      window.addEventListener('resize', resize);
      document.addEventListener('visibilitychange', onVisibilityChange);
      resize();

      const start = performance.now();
      const render = (now: number) => {
        if (disposed) {
          return;
        }

        if (isVisible && isTabVisible) {
          const elapsed = reducedMotion ? TIMELINE_SECONDS : ((now - start) / 1000) % TIMELINE_SECONDS;
          const progress = reducedMotion ? 1 : elapsed / TIMELINE_SECONDS;
          progressRef.current = progress;

          const sweep = smoothstep(0.1, 0.62, progress);
          const collapse = smoothstep(0.55, 0.86, progress);
          const pulse = Math.sin(now * 0.0035) * 0.5 + 0.5;

          world.rotation.y = Math.sin(now * 0.00022) * 0.12;
          upperGrid.position.y = 2.1 + Math.sin(now * 0.0012) * 0.16;
          heatGroup.rotation.y = now * 0.00016;
          lowerGrid.material.opacity = 0.16 + sweep * 0.16 + pulse * 0.05;
          upperGrid.material.opacity = 0.24 + sweep * 0.22;
          strands.material.opacity = 0.24 + collapse * 0.5;
          pointsMaterial.opacity = 0.36 + sweep * 0.3;
          points.rotation.y = now * 0.00035;
          spikeGroup.rotation.y = -now * 0.0003;

          const positions = pointsGeometry.attributes.position as BufferAttribute;
          for (let i = 0; i < pointCount; i += 1) {
            const baseY = -1.9 + ((i * 29) % 100) * 0.038;
            positions.setY(i, baseY + Math.sin(now * 0.002 + pointSeeds[i]) * (0.08 + collapse * 0.2));
          }
          positions.needsUpdate = true;

          heatMaterials.forEach((material, index) => {
            const wave = Math.sin(now * 0.004 + index * 0.43) * 0.5 + 0.5;
            material.opacity = 0.04 + sweep * 0.1 + wave * 0.14 * (0.35 + collapse);
          });

          renderer.render(scene, camera);
        }

        frameId = requestAnimationFrame(render);
      };

      frameId = requestAnimationFrame(render);

      return () => {
        observer.disconnect();
        window.removeEventListener('resize', resize);
        document.removeEventListener('visibilitychange', onVisibilityChange);
        cancelAnimationFrame(frameId);
        renderer.dispose();
        cellGeometry.dispose();
        pointsGeometry.dispose();
        pointsMaterial.dispose();
        strandsGeometry.dispose();
        strandsMaterial.dispose();
        spikeGeometry.dispose();
        heatMaterials.forEach((material) => material.dispose());
        lowerGrid.geometry.dispose();
        upperGrid.geometry.dispose();
        lowerGrid.material.dispose();
        upperGrid.material.dispose();
        renderer.domElement.remove();
      };
    }

    let cleanup: (() => void) | undefined;
    runScene(mountElement).then((disposeScene) => {
      cleanup = disposeScene;
    });

    return () => {
      disposed = true;
      cleanup?.();
    };
  }, [progressRef, reducedMotion]);

  return <div ref={mountRef} className={styles.scene} aria-hidden="true" />;
}

function TokenField({
  tokens,
  progress,
}: {
  tokens: DemoToken[];
  progress: number;
}) {
  const sweep = smoothstep(0.08, 0.6, progress);
  const collapse = smoothstep(0.55, 0.86, progress);

  return (
    <div className={styles.tokenField} aria-label="Original text token scoring visualization">
      {tokens.map((token, index) => {
        const scanPosition = index / Math.max(tokens.length - 1, 1);
        const scanned = sweep >= scanPosition;
        const deleteOpacity = token.keep ? 1 : 1 - collapse * 0.72;
        const scoreGlow = scanned ? token.keepScore : 0;
        return (
          <Fragment key={`${token.text}-${index}`}>
            <span
              className={clsx(styles.token, styles[token.role], {
                [styles.scanned]: scanned,
                [styles.kept]: token.keep && collapse > 0.25,
                [styles.deleted]: !token.keep && collapse > 0.25,
              })}
              style={
                {
                  '--score': scoreGlow.toFixed(2),
                  '--token-opacity': deleteOpacity.toFixed(2),
                  '--token-shift': `${collapse * (token.keep ? -2 : 8)}px`,
                } as React.CSSProperties
              }>
              {token.text}
            </span>{' '}
          </Fragment>
        );
      })}
    </div>
  );
}

function CompressedLane({
  tokens,
  progress,
}: {
  tokens: DemoToken[];
  progress: number;
}) {
  const reveal = smoothstep(0.66, 0.95, progress);
  const keptTokens = tokens.filter((token) => token.keep);

  return (
    <div className={styles.compressedLane}>
      <div className={styles.laneHeader}>
        <span>compressed sequence</span>
        <strong>{Math.round((1 - keptTokens.length / tokens.length) * 100)}% saved</strong>
      </div>
      <p>
        {keptTokens.map((token, index) => {
          const tokenReveal = reveal >= index / Math.max(keptTokens.length - 1, 1);
          return (
            <span
              // eslint-disable-next-line react/no-array-index-key
              key={`${token.text}-kept-${index}`}
              className={clsx(styles.outputToken, {[styles.outputVisible]: tokenReveal})}>
              {token.text}
            </span>
          );
        })}
      </p>
    </div>
  );
}

function ShowcaseInner(): ReactNode {
  const reducedMotion = useReducedMotion();
  const progressRef = useRef(reducedMotion ? 1 : 0);
  const [progress, setProgress] = useState(reducedMotion ? 1 : 0);
  const tokens = useMemo(() => DEMO_TOKENS, []);

  useEffect(() => {
    if (reducedMotion) {
      setProgress(1);
      progressRef.current = 1;
      return undefined;
    }

    let frameId = 0;
    const syncProgress = () => {
      setProgress(progressRef.current);
      frameId = requestAnimationFrame(syncProgress);
    };
    frameId = requestAnimationFrame(syncProgress);
    return () => cancelAnimationFrame(frameId);
  }, [progressRef, reducedMotion]);

  return (
    <section className={styles.showcase}>
      <div className={styles.canvasLayer}>
        <CompressionScene progressRef={progressRef} reducedMotion={reducedMotion} />
      </div>
      <div className={styles.noiseLayer} aria-hidden="true" />
      <div className={styles.chromaticLayer} aria-hidden="true" />

      <div className={styles.content}>
        <div className={styles.copyColumn}>
          <span className={styles.eyebrow}>token-level context compression</span>
          <h1>ContextCrumb keeps the signal and shakes off the padding.</h1>
          <p className={styles.lede}>
            A small model scores every token before your agent spends context on it. Low-value
            words dim out; names, actions, constraints, and order stay intact.
          </p>
          <div className={styles.actions}>
            <Link className={styles.primaryAction} to="/docs/overview">
              Read the docs
            </Link>
            <Link
              className={styles.secondaryAction}
              to="https://huggingface.co/spaces/ymao20/contextcrumb-32m-demo">
              Open playground
            </Link>
          </div>
        </div>

        <div className={styles.analysisPanel}>
          <div className={styles.panelTopline}>
            <span>attention pass</span>
            <span>{Math.round(smoothstep(0.08, 0.6, progress) * 100)}%</span>
          </div>
          <TokenField tokens={tokens} progress={progress} />
          <CompressedLane tokens={tokens} progress={progress} />
          <div className={styles.statsRow}>
            <span>
              <strong>{tokens.length}</strong> input tokens
            </span>
            <span>
              <strong>{tokens.filter((token) => token.keep).length}</strong> kept
            </span>
            <span>
              <strong>same</strong> order
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}

function ShowcaseFallback(): ReactNode {
  const keptTokens = DEMO_TOKENS.filter((token) => token.keep);

  return (
    <section className={styles.showcase}>
      <div className={styles.staticBackdrop} aria-hidden="true" />
      <div className={styles.content}>
        <div className={styles.copyColumn}>
          <span className={styles.eyebrow}>token-level context compression</span>
          <h1>ContextCrumb keeps the signal and shakes off the padding.</h1>
          <p className={styles.lede}>
            A small model scores every token before your agent spends context on it.
          </p>
        </div>
        <div className={styles.analysisPanel}>
          <TokenField tokens={DEMO_TOKENS} progress={1} />
          <CompressedLane tokens={DEMO_TOKENS} progress={1} />
          <div className={styles.statsRow}>
            <span>
              <strong>{DEMO_TOKENS.length}</strong> input tokens
            </span>
            <span>
              <strong>{keptTokens.length}</strong> kept
            </span>
            <span>
              <strong>same</strong> order
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}

export default function CompressionShowcase(): ReactNode {
  return <BrowserOnly fallback={<ShowcaseFallback />}>{() => <ShowcaseInner />}</BrowserOnly>;
}

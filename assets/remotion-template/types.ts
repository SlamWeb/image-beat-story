export type TransitionMode = 'dissolve' | 'press' | 'pulse' | 'bounce';

export type Shot = {
  id: string;
  src: string;
  impactFrame: number;
  preFrames: number;
  postFrames: number;
  releaseFrames: number;
  intensity: number;
  eventType: string;
  transition?: TransitionMode;
};

export type Motion = {
  attackFrames: number;
  environmentBaseScale: number;
  environmentContraction: number;
  environmentRebound: number;
  environmentPressPixels: number;
  environmentReboundPixels: number;
  environmentOrigin: string;
  environmentEV: number;
  subjectBrightnessDrop: number;
  subjectBrightnessRebound: number;
  subjectContraction: number;
  subjectRebound: number;
  subjectPressPixels: number;
  subjectShakePixels: number;
  subjectOrigin: string;
  reboundPeakFrames: number;
  reboundWidthFrames: number;
  shakeRadiansPerFrame: number;
  shakeDecayFrames: number;
  releaseDecay: number;
};

export type Timeline = {
  schemaVersion: 1;
  width: number;
  height: number;
  fps: number;
  durationInFrames: number;
  audio?: {src: string; fadeOutSeconds?: number};
  shots: Shot[];
  mode?: TransitionMode;
  motion?: Partial<Motion>;
  subjectMask?: string;
};

export const DEFAULT_MOTION: Motion = {
  attackFrames: 3,
  environmentBaseScale: 1.07,
  environmentContraction: 0.058,
  environmentRebound: 0.019,
  environmentPressPixels: 7,
  environmentReboundPixels: 2,
  environmentOrigin: '50% 50%',
  environmentEV: 0,
  subjectBrightnessDrop: 0.28,
  subjectBrightnessRebound: 0.045,
  subjectContraction: 0.025,
  subjectRebound: 0.009,
  subjectPressPixels: 4,
  subjectShakePixels: 2.5,
  subjectOrigin: '50% 50%',
  reboundPeakFrames: 5.5,
  reboundWidthFrames: 3.4,
  shakeRadiansPerFrame: Math.PI * 0.75,
  shakeDecayFrames: 3.4,
  releaseDecay: 3.8,
};

const modes = new Set(['dissolve', 'press', 'pulse', 'bounce']);

// Fail before rendering rather than silently sorting or retiming authored events.
export const validateTimeline = (value: unknown): Timeline => {
  const t = value as Timeline;
  const positiveInteger = (n: number) => Number.isInteger(n) && n > 0;
  const nonnegativeInteger = (n: number) => Number.isInteger(n) && n >= 0;
  const finite = (n: number) => typeof n === 'number' && Number.isFinite(n);
  const asset = (s: unknown) => typeof s === 'string' && s.length > 0 &&
    !s.startsWith('/') && !s.includes('\\') && !s.split('/').includes('..') && !s.includes(':');
  if (!t || t.schemaVersion !== 1 || !positiveInteger(t.width) || !positiveInteger(t.height) ||
    !finite(t.fps) || t.fps <= 0 || !positiveInteger(t.durationInFrames) || !Array.isArray(t.shots) || !t.shots.length) {
    throw new Error('timeline: require schemaVersion=1, positive dimensions/fps/duration, and nonempty shots');
  }
  if (t.mode !== undefined && !modes.has(t.mode)) throw new Error('timeline: invalid mode');
  const ids = new Set<string>();
  t.shots.forEach((s, i) => {
    if (!s || typeof s.id !== 'string' || !s.id || ids.has(s.id) || !asset(s.src) ||
      !nonnegativeInteger(s.impactFrame) || s.impactFrame >= t.durationInFrames ||
      !nonnegativeInteger(s.preFrames) || !positiveInteger(s.postFrames) || !positiveInteger(s.releaseFrames) ||
      !finite(s.intensity) || s.intensity < 0 || s.intensity > 1 || typeof s.eventType !== 'string' ||
      (s.transition !== undefined && !modes.has(s.transition))) {
      throw new Error(`timeline: invalid shot at index ${i}`);
    }
    ids.add(s.id);
    if (i === 0 && (s.impactFrame !== 0 || s.preFrames !== 0)) throw new Error('timeline: first shot requires impactFrame=0, preFrames=0');
    if (i > 0 && (s.impactFrame <= t.shots[i - 1].impactFrame || s.preFrames === 0 || s.preFrames > s.impactFrame)) {
      throw new Error(`timeline: shot ${s.id} requires increasing impactFrame and positive preFrames <= impactFrame`);
    }
  });
  if (t.subjectMask !== undefined && !asset(t.subjectMask)) throw new Error('timeline: subjectMask must be a public-relative path');
  if (t.audio && (!asset(t.audio.src) || (t.audio.fadeOutSeconds !== undefined &&
    (!finite(t.audio.fadeOutSeconds) || t.audio.fadeOutSeconds < 0)))) throw new Error('timeline: invalid audio');
  if (t.motion) {
    Object.entries(t.motion).forEach(([key, n]) => {
      if (!(key in DEFAULT_MOTION) || typeof n !== typeof DEFAULT_MOTION[key as keyof Motion] ||
        (typeof n === 'number' && !finite(n))) throw new Error(`timeline: invalid motion.${key}`);
    });
  }
  const p = {...DEFAULT_MOTION, ...t.motion};
  if (p.attackFrames <= 0 || p.reboundWidthFrames <= 0 || p.shakeDecayFrames <= 0 || p.releaseDecay <= 0 ||
    p.environmentBaseScale <= 0 || p.subjectBrightnessDrop < 0 || p.subjectBrightnessDrop > 1) {
    throw new Error('timeline: invalid motion range');
  }
  return t;
};

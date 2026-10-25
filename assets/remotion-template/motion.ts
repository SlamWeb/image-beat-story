import {DEFAULT_MOTION, type Motion, type Shot, type Timeline, type TransitionMode} from './types';

export const clamp = (x: number) => Math.min(1, Math.max(0, x));
export const smooth = (x: number) => {const t = clamp(x); return t * t * (3 - 2 * t);};

// The detected impact is always the 50% picture blend, even for asymmetric fades.
export const mixProgress = (frame: number, shot: Shot) => {
  if (shot.impactFrame === 0 && shot.preFrames === 0) return 1;
  const dt = frame - shot.impactFrame;
  const phase = dt <= 0 ? 0.5 * (dt + shot.preFrames) / shot.preFrames : 0.5 + 0.5 * dt / shot.postFrames;
  return smooth(phase);
};

export const modeFor = (timeline: Timeline, shot: Shot): TransitionMode => shot.transition ?? timeline.mode ?? 'press';
export const parameters = (timeline: Timeline): Motion => ({...DEFAULT_MOTION, ...timeline.motion});

// All release tails coexist. A new note never resets the preceding note's decay.
// Optional mode filtering lets pulse/bounce events affect only the intended layer.
export const motionAt = (frame: number, timeline: Timeline, accepts: (mode: TransitionMode) => boolean = m => m !== 'dissolve') => {
  const p = parameters(timeline);
  let remaining = 1;
  let rebound = 0;
  let shake = 0;
  for (const shot of timeline.shots) {
    if (!accepts(modeFor(timeline, shot))) continue;
    const dt = frame - shot.impactFrame;
    if (dt < -p.attackFrames || dt > shot.releaseFrames) continue;
    const envelope = dt < 0 ? smooth((dt + p.attackFrames) / p.attackFrames)
      : Math.exp(-p.releaseDecay * dt / shot.releaseFrames) *
        (1 - smooth((dt - shot.releaseFrames * 0.8) / (shot.releaseFrames * 0.2)));
    remaining *= 1 - shot.intensity * envelope;
    if (dt >= 0) {
      rebound += shot.intensity * Math.exp(-Math.pow((dt - p.reboundPeakFrames) / p.reboundWidthFrames, 2));
      shake += shot.intensity * Math.sin(dt * p.shakeRadiansPerFrame) * Math.exp(-dt / p.shakeDecayFrames);
    }
  }
  return {press: 1 - remaining, rebound: Math.min(1.15, rebound), shake};
};

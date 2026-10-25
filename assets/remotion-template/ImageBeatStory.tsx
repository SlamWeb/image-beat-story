import React from 'react';
import {AbsoluteFill, CanvasImage, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Audio} from '@remotion/media';
import {mixProgress, modeFor, motionAt, parameters, smooth} from './motion';
import type {Shot, Timeline} from './types';

const Picture: React.FC<{shot: Shot; initial: boolean; start: number}> = ({shot, initial, start}) => {
  const frame = useCurrentFrame() + start;
  const {fps} = useVideoConfig();
  return <AbsoluteFill style={{opacity: initial ? 1 : mixProgress(frame, shot)}}>
    <CanvasImage src={staticFile(shot.src)} premountFor={fps} style={{width: '100%', height: '100%', objectFit: 'cover'}}/>
  </AbsoluteFill>;
};

// This is intentionally a data-generated template: timeline.json owns its shots.
// Both environment and protected layer use the very same Worlds and blend clock.
const Worlds: React.FC<{timeline: Timeline}> = ({timeline}) => {
  const {fps} = useVideoConfig();
  return <AbsoluteFill>{timeline.shots.map((shot, index) => {
    const next = timeline.shots[index + 1];
    const start = index === 0 ? 0 : shot.impactFrame - shot.preFrames;
    const end = next ? Math.min(timeline.durationInFrames, next.impactFrame + next.postFrames) : timeline.durationInFrames;
    return <Sequence key={shot.id} from={start} durationInFrames={end - start} premountFor={fps} name={`${shot.id} / ${modeFor(timeline, shot)}`}>
      <Picture shot={shot} initial={index === 0} start={start}/>
    </Sequence>;
  })}</AbsoluteFill>;
};

export const ImageBeatStory: React.FC<{timeline: Timeline}> = ({timeline}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const p = parameters(timeline);
  const environment = motionAt(frame, timeline);
  const brightness = motionAt(frame, timeline, m => m === 'pulse' || m === 'bounce');
  const subject = motionAt(frame, timeline, m => m === 'bounce');
  const movingEnvironment = timeline.shots.some(s => modeFor(timeline, s) !== 'dissolve');
  const subjectBrightness = Math.max(0, 1 - p.subjectBrightnessDrop * brightness.press + p.subjectBrightnessRebound * brightness.rebound);
  const mask = timeline.subjectMask ? `url("${staticFile(timeline.subjectMask)}")` : undefined;
  const gain = Math.pow(2, p.environmentEV);
  const unmaskedSubjectScale = mask ? 1 : 1 - p.subjectContraction * subject.press + p.subjectRebound * subject.rebound;
  const unmaskedSubjectY = mask ? 0 : p.subjectPressPixels * subject.press + p.subjectShakePixels * subject.shake;
  const environmentY = p.environmentPressPixels * environment.press - p.environmentReboundPixels * environment.rebound + unmaskedSubjectY;
  const environmentScale = (movingEnvironment ? p.environmentBaseScale - p.environmentContraction * environment.press + p.environmentRebound * environment.rebound : 1) * unmaskedSubjectScale;
  // With one full-image layer the two contractions combine. Keep center-origin
  // movement inside the crop instead of revealing the composition background.
  const cropSafeScale = !mask && movingEnvironment ? Math.max(environmentScale, 1 + 2 * (Math.abs(environmentY) + 1) / timeline.height) : environmentScale;
  const environmentFilters = [p.environmentEV === 0 ? '' : 'url(#image-beat-exposure)',
    !mask && subjectBrightness !== 1 ? `brightness(${subjectBrightness})` : ''].filter(Boolean).join(' ');
  const fadeFrames = Math.min(durationInFrames, (timeline.audio?.fadeOutSeconds ?? 0.35) * fps);
  const audioVolume = fadeFrames <= 0 ? 1 : 1 - smooth((frame - (durationInFrames - fadeFrames)) / Math.max(1, fadeFrames - 1));
  return <AbsoluteFill style={{backgroundColor: '#17171b', overflow: 'hidden'}}>
    <svg width="0" height="0" aria-hidden style={{position: 'absolute'}}>
      <defs><filter id="image-beat-exposure" colorInterpolationFilters="linearRGB">
        <feComponentTransfer><feFuncR type="linear" slope={gain}/><feFuncG type="linear" slope={gain}/><feFuncB type="linear" slope={gain}/></feComponentTransfer>
      </filter></defs>
    </svg>
    <AbsoluteFill style={{
      scale: cropSafeScale,
      translate: `0px ${environmentY}px`,
      transformOrigin: p.environmentOrigin,
      filter: environmentFilters || undefined,
    }}><Worlds timeline={timeline}/></AbsoluteFill>
    {mask ? <AbsoluteFill style={{
      scale: 1 - p.subjectContraction * subject.press + p.subjectRebound * subject.rebound,
      translate: `0px ${p.subjectPressPixels * subject.press + p.subjectShakePixels * subject.shake}px`,
      transformOrigin: p.subjectOrigin,
      filter: subjectBrightness === 1 ? undefined : `brightness(${subjectBrightness})`,
    }}><AbsoluteFill style={{maskImage: mask, WebkitMaskImage: mask, maskMode: 'alpha',
      maskSize: '100% 100%', WebkitMaskSize: '100% 100%', maskRepeat: 'no-repeat', WebkitMaskRepeat: 'no-repeat'}}>
      <Worlds timeline={timeline}/>
    </AbsoluteFill></AbsoluteFill> : null}
    {timeline.audio ? <Audio src={staticFile(timeline.audio.src)} playbackRate={1} volume={audioVolume} premountFor={fps} durationInFrames={durationInFrames}/> : null}
  </AbsoluteFill>;
};

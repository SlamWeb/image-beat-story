import React from 'react';
import {Composition, registerRoot} from 'remotion';
import timelineJSON from './timeline.json';
import {ImageBeatStory} from './ImageBeatStory';
import {validateTimeline} from './types';

const timeline = validateTimeline(timelineJSON);
const Root = () => <Composition id="ImageBeatStory" component={ImageBeatStory}
  width={timeline.width} height={timeline.height} fps={timeline.fps}
  durationInFrames={timeline.durationInFrames} defaultProps={{timeline}}/>;
registerRoot(Root);

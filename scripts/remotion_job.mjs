// Render the staged template using an existing compatible Remotion runtime.
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';

const args = {};
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i];
  if (key === '--help') {
    console.log('node remotion_job.mjs --project DIR --runtime REMOTION_PROJECT --output FILE [--still-frame N] [--browser-executable CHROME] [--concurrency 2]');
    process.exit(0);
  }
  if (!key.startsWith('--') || !process.argv[i + 1]) throw new Error(`Missing value for ${key}`);
  args[key.slice(2)] = process.argv[i + 1];
}
for (const key of ['project', 'runtime', 'output']) if (!args[key]) throw new Error(`--${key} is required`);
const project = path.resolve(args.project);
const runtime = path.resolve(args.runtime);
const output = path.resolve(args.output);
if (fs.existsSync(output)) throw new Error('Output exists; use a new version filename.');
const requireRuntime = createRequire(path.join(runtime, 'package.json'));
const {bundle} = requireRuntime('@remotion/bundler');
const {selectComposition, renderMedia, renderStill} = requireRuntime('@remotion/renderer');
const timeline = JSON.parse(fs.readFileSync(path.join(project, 'timeline.json'), 'utf8'));
const started = new Date().toISOString();
const browserExecutable = args['browser-executable'] ? path.resolve(args['browser-executable']) : undefined;
const serveUrl = await bundle({
  entryPoint: path.join(project, 'index.tsx'),
  publicDir: path.join(project, 'public'),
  webpackOverride: config => ({...config, resolve: {...config.resolve,
    modules: [path.join(runtime, 'node_modules'), ...(config.resolve?.modules ?? ['node_modules'])]}}),
});
const composition = await selectComposition({serveUrl, id: 'ImageBeatStory', browserExecutable});
if (composition.durationInFrames !== timeline.durationInFrames || composition.fps !== timeline.fps ||
    composition.width !== timeline.width || composition.height !== timeline.height) {
  throw new Error('Selected composition does not match the staged timeline.');
}
fs.mkdirSync(path.dirname(output), {recursive: true});
const still = args['still-frame'] !== undefined;
if (still) {
  const frame = Number(args['still-frame']);
  if (!Number.isInteger(frame) || frame < 0 || frame >= timeline.durationInFrames) throw new Error('Invalid still frame');
  await renderStill({serveUrl, composition, output, frame, imageFormat: 'png', browserExecutable, logLevel: 'warn'});
} else {
  const concurrency = Number(args.concurrency ?? 2);
  if (!Number.isInteger(concurrency) || concurrency < 1) throw new Error('Invalid concurrency');
  await renderMedia({serveUrl, composition, outputLocation: output, codec: 'h264',
    audioCodec: 'aac', pixelFormat: 'yuv420p', crf: 18, concurrency, browserExecutable, logLevel: 'warn'});
}
const receipt = {started, completed: new Date().toISOString(), stage: still ? 'still_rendered' : 'video_rendered',
  output, bytes: fs.statSync(output).size, project, runtime,
  composition: {id: composition.id, fps: composition.fps, width: composition.width,
    height: composition.height, durationInFrames: composition.durationInFrames},
  fullDecodeVerified: false, visualListeningReview: 'not_established_by_rendering'};
fs.writeFileSync(`${output}.render-receipt.json`, JSON.stringify(receipt, null, 2), {flag: 'wx'});
console.log(JSON.stringify(receipt, null, 2));

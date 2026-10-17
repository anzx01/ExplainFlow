import {test} from "node:test";
import assert from "node:assert/strict";
import {timedRevealPaths} from "./reveal-timing.mjs";

test("objects stay in their spoken windows instead of being scattered across cues", () => {
  const paths = Array.from({length: 6}, (_, index) => ({points:[{x:index / 6,y:0.5}]}));
  const cues = [{text:"先看手机",startFrame:0},{text:"继续讲手机",startFrame:120},{text:"再看大脑",startFrame:240,endFrame:480}];
  const beats = [{untilX:0.5,phrase:"手机"},{untilX:1,phrase:"大脑"}];
  const result = timedRevealPaths(paths,cues,beats,480);
  assert.equal(result[0].inkStart,0);
  assert.equal(result[2].colorEnd,240);
  assert.equal(result[3].inkStart,240);
  assert.equal(result[5].colorEnd,480);
  assert(result.slice(0,3).every(p=>p.points[0].x<0.5));
  assert(result.slice(3).every(p=>p.points[0].x>=0.5));
  assert(result.every(p=>p.colorStart>=p.inkEnd));
  assert.throws(()=>timedRevealPaths(paths,[],[],480), /No subtitle cues/);
  assert.throws(()=>timedRevealPaths(paths,cues,[{untilX:1,phrase:"不存在"}],480), /No spoken cue/);
});

test("last object finishes before narration switches to a new action", () => {
  const cues = [{text:"右边的手机",startFrame:0,endFrame:60},
    {text:"把手机放远",startFrame:60,endFrame:100},
    {text:"先完成一小段专注练习",startFrame:100,endFrame:180}];
  const result = timedRevealPaths([{points:[{x:.8,y:.5}]}], cues,
    [{untilX:1,phrase:"右边的手机",endBefore:"把手机放远"}],180);
  assert.equal(result.at(-1).colorEnd,60);
  assert.throws(()=>timedRevealPaths([{points:[{x:.8,y:.5}]}],cues,
    [{untilX:1,phrase:"右边的手机",endBefore:"不存在"}],180), /visual boundary/);
});

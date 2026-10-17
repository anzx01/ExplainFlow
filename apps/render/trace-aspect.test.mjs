import {test} from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {join} from "node:path";
import sharp from "sharp";
import {buildRasterRevealFromBuffer, rasterCoveragePaths} from "./trace.mjs";
import {PUBLIC_GENERATED_DIR} from "./config.mjs";

test("landscape artwork stays landscape with matching ink and color geometry", async()=>{
  const fixture = Buffer.from('<svg width="720" height="300"><rect width="720" height="300" fill="white"/><path d="M50 70 H660 V230 H50 Z" fill="#d99b4a" stroke="#302820" stroke-width="8"/></svg>');
  const result = await buildRasterRevealFromBuffer(fixture,`test-aspect-${process.pid}`,{id:"landscape"},{forceTrace:true});
  assert(result.rasterReveal.imageWidth/result.rasterReveal.imageHeight>2);
  const jobDir=join(PUBLIC_GENERATED_DIR,`test-aspect-${process.pid}`);
  for(const name of ["landscape-master.png","landscape.png","landscape-color.png"]) {
    const meta=await sharp(readFileSync(join(jobDir,name))).metadata();
    assert.equal(meta.width,result.rasterReveal.imageWidth);
    assert.equal(meta.height,result.rasterReveal.imageHeight);
  }
  assert(result.rasterReveal.strokes.length>0);
});

test("paint coverage paths reveal filled interiors, not only sparse contour edges", async()=>{
  const width=400,height=240;
  const fixture=await sharp(Buffer.from('<svg width="400" height="240"><rect x="35" y="20" width="300" height="195" fill="#cd672b"/><circle cx="365" cy="220" r="3" fill="#274f25"/></svg>')).png().toBuffer();
  const paths=await rasterCoveragePaths(fixture);
  assert(paths.length>20);
  assert(paths[0].points[0].y>.3&&paths[0].points[0].y<.7,"Start on the main subject, not the top border");
  const strokes=paths.map(p=>`<path d="M${p.points[0].x*width} ${p.points[0].y*height} L${p.points[1].x*width} ${p.points[1].y*height}" stroke="white" stroke-width="${Math.max(18,p.revealWidth*Math.max(width,height))}" stroke-linecap="round"/>`).join('');
  const mask=await sharp(Buffer.from(`<svg width="${width}" height="${height}"><rect width="100%" height="100%" fill="black"/>${strokes}</svg>`)).removeAlpha().raw().toBuffer();
  const source=await sharp(fixture).ensureAlpha().raw().toBuffer();
  let painted=0,visible=0;
  for(let i=0;i<width*height;i++) if(source[i*4+3]>32) {painted++;if(mask[i*3]>200) visible++;}
  assert(visible/painted>.99,`Only ${visible/painted} of painted pixels revealed`);
  assert.deepEqual(await rasterCoveragePaths(await sharp({create:{width:20,height:20,channels:4,background:'#00000000'}}).png().toBuffer()),[]);
});

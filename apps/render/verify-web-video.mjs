// Exercise the real web preview, not just the exported file's stream headers.
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {readFileSync,writeFileSync} from "node:fs";
import {openBrowser} from "@remotion/renderer";

const jobId=process.argv[2]??"sugar-harms-local-flux-v4";
const title=process.argv[3]??"多吃糖的坏处（本地彩色插画";
const expectedDuration=Number(process.argv[4]??101.6);
const jobs=JSON.parse(readFileSync("../../outputs/jobs.json","utf8"));
const mediaUrl=`http://localhost:3002/download/${jobId}`;
const downloaded=Buffer.from(await (await fetch(mediaUrl)).arrayBuffer());
assert.equal(createHash("sha256").update(downloaded).digest("hex"),createHash("sha256").update(readFileSync(jobs[jobId].outputPath)).digest("hex"));
const browser=await openBrowser("chrome",{browserExecutable:"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"});
try {
  const page=await browser.newPage({context:()=>null,logLevel:"error",indent:false,pageIndex:0,onBrowserLog:null,onLog:()=>{}});
  await page.goto({url:"http://localhost:3010/jobs",timeout:90000});
  await page.evaluate(async(title)=>{
    for(let i=0;i<100;i++) {
      const row=[...document.querySelectorAll("tr")].find(r=>r.textContent.includes(title));
      const button=row&&[...row.querySelectorAll("button")].find(b=>b.textContent.trim()==="预览");
      if(button) {button.click();return;}
      await new Promise(r=>setTimeout(r,200));
    }
    throw Error("Latest video missing from the visible jobs list");
  },title);
  const result=await page.evaluate(async()=>{
    for(let i=0;i<100&&!document.querySelector("video");i++) await new Promise(r=>setTimeout(r,100));
    const video=document.querySelector("video");
    if(!video) throw Error("Missing preview player");
    video.crossOrigin="anonymous";
    video.load();
    for(let i=0;i<100&&video.readyState<2;i++) await new Promise(r=>setTimeout(r,100));
    const context=new AudioContext();
    await context.resume();
    const source=context.createMediaElementSource(video), analyser=context.createAnalyser();
    source.connect(analyser);analyser.connect(context.destination);
    video.muted=true;video.volume=0;video.playbackRate=2;
    [...document.querySelectorAll("button")].find(b=>b.textContent.includes("正常速度 · 有声播放")).click();
    const begin=performance.now(),start=video.currentTime;
    let energy=0,samples=0;
    const data=new Float32Array(analyser.fftSize);
    for(let i=0;i<60;i++) {
      await new Promise(r=>setTimeout(r,100));
      analyser.getFloatTimeDomainData(data);
      for(const sample of data) {energy+=sample*sample;samples++;}
    }
    const result={src:video.currentSrc,duration:video.duration,playbackRate:video.playbackRate,
      muted:video.muted,volume:video.volume,paused:video.paused,error:video.error?.message??null,
      elapsedMedia:video.currentTime-start,elapsedWall:(performance.now()-begin)/1000,
      audioRms:Math.sqrt(energy/samples),audioDecodedBytes:video.webkitAudioDecodedByteCount};
    video.pause();await context.close();return result;
  });
  assert.equal(result.src,mediaUrl);
  assert.equal(result.playbackRate,1);
  assert.equal(result.muted,false);
  assert.equal(result.volume,1);
  assert.equal(result.paused,false,result.error);
  assert(Math.abs(result.duration-expectedDuration)<1);
  assert(Math.abs(result.elapsedMedia-result.elapsedWall)<.7,JSON.stringify(result));
  assert(result.audioRms>.005,`Browser output is silent: ${JSON.stringify(result)}`);
  const screenshot=await page._client().send("Page.captureScreenshot",{format:"png"});
  writeFileSync(`../../outputs/${jobId}-web-preview.png`,Buffer.from(screenshot.value.data,"base64"));
  writeFileSync(`../../outputs/${jobId}-web-check.json`,JSON.stringify(result,null,2));
  console.log(JSON.stringify(result,null,2));
} finally {await browser.close({silent:true});}

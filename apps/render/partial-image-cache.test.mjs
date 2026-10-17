import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import sharp from "sharp";

test("partial generation caches good scenes and retries only missing artwork", async () => {
  const image = (await sharp({create:{width:320,height:240,channels:3,background:"white"}})
    .composite([{input:Buffer.from('<svg width="320" height="240"><rect x="60" y="50" width="200" height="140" rx="30" fill="#ea6d42" stroke="black" stroke-width="8"/></svg>')}])
    .png().toBuffer()).toString("base64");
  const requests=[];
  const server=http.createServer(async(req,res)=>{
    res.setHeader("Content-Type","application/json");
    if(req.method==="GET") {res.end(JSON.stringify({provider:"local",timeoutSeconds:120,maxAttempts:3}));return;}
    let body="";
    for await (const chunk of req) body+=chunk;
    const scenes=JSON.parse(body).scenes;
    requests.push(scenes.map(s=>s.scene_id));
    const images=Object.fromEntries(scenes.map(s=>[s.scene_id,requests.length===1&&s.scene_id==="bad"?null:image]));
    res.end(JSON.stringify({images,diagnostics:{bad:{attempts:[{errors:["possible_readable_text_or_signature"]}]}}}));
  });
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  process.env.PYTHON_API_URL=`http://127.0.0.1:${server.address().port}`;
  process.env.SKIP_IMAGE_TRACE="0";
  process.env.REMOTION_IMAGE_TRACE="1";
  try {
    const {injectImageTraces}=await import("./trace-inject.mjs");
    const storyboard={topic:`partial-cache-test-${process.pid}-${Date.now()}`,scenes:["good","bad"].map(id=>({
      id,title:id,image_description:"A colored rounded object",board_mode:"whiteboard",hand_usage:"trace",video_style:"whiteboard",
    }))};
    await assert.rejects(injectImageTraces(storyboard,`partial-cache-${process.pid}-first`),/successful artwork cached.*bad: possible_readable_text_or_signature/);
    const result=await injectImageTraces(storyboard,`partial-cache-${process.pid}-retry`);
    assert.deepEqual(requests,[["good","bad"],["bad"]]);
    assert(result.scenes.every(scene=>scene.rasterReveal));
  } finally {await new Promise(resolve=>server.close(resolve));}
});

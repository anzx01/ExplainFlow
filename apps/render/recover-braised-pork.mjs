// Recover source intent and the existing continuous narration from the failed job audit.
import assert from "node:assert/strict";
import {readFileSync,writeFileSync} from "node:fs";
import {resolve} from "node:path";
import sharp from "sharp";
const root=resolve("../..");
const read=path=>JSON.parse(readFileSync(resolve(root,path),"utf8"));
const source=read("apps/render/public/generated/7cbfef27-9aad-4f88-b076-84d7667f2858/image-generation-request.json");
const phrases=read("outputs/audio/continuous_73d0e59d4c622f69e94c-text.json");
// The inspected first illustration has a tiny synthetic signature outside the subject.
await sharp(resolve(root,"image/braised-pork-recovery/scene_0-clean.png"))
  .composite([{input:await sharp({create:{width:40,height:30,channels:3,background:"white"}}).png().toBuffer(),left:580,top:605}])
  .png().toFile(resolve(root,"image/braised-pork-recovery/scene_0-final.png"));
const labels=[["胶原蛋白","明胶","小火慢炖"],["带皮五花","冷水焯水"],["小火","枣红色","避免发苦"],["热水","小火慢炖"],["汤汁浓缩","翻动防糊"],["五步流程","红亮软糯"]];
const scenes=[...source.scenes].sort((a,b)=>a.scene_id.localeCompare(b.scene_id)).map((item,index)=>{
  const diagnostics=read(`image/braised-pork-recovery/${item.scene_id}-clean.json`);
  assert(diagnostics.ok);
  const narration=phrases.filter(p=>p.scene===index).map(p=>p.text).join("");
  assert(narration);
  return {id:item.scene_id,order:index,title:item.title,narration,duration_estimate:20,animations:[],
    image_description:diagnostics.prompt,reference_image_path:resolve(root,`image/braised-pork-recovery/${item.scene_id}-${index===0?"final":"clean"}.png`),
    board_mode:"whiteboard",hand_usage:"trace",render_strategy:"hybrid",video_style:"whiteboard",visual_style:"teacher_whiteboard",pen_style:"marker",
    diagram_plan:{kind:"process",required_labels:labels[index]},
  };
});
const payload={storyboard:{topic:"红烧肉制作：从选肉到收汁（本地插画修复版）",video_style:"whiteboard",pen_style:"marker",image_generation_mode:"flux",total_duration_estimate:120,scenes},subtitlesEnabled:true,forceRender:true};
writeFileSync(resolve(root,"image/braised-pork-recovery/render-request.json"),JSON.stringify(payload,null,2));
const response=await fetch("http://localhost:3002/render",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
assert(response.ok,await response.clone().text());
const job=await response.json();
writeFileSync(resolve(root,"image/braised-pork-recovery/render-job.json"),JSON.stringify(job,null,2));
console.log(JSON.stringify(job));

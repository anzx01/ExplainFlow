// Reuse inspected local FLUX paintings; each shot explains only its visible subject.
import assert from "node:assert/strict";
import {mkdirSync, readFileSync, writeFileSync} from "node:fs";
import {resolve} from "node:path";
import sharp from "sharp";

const root=resolve("../..");
const folder=resolve(root,"image/braised-pork-sync");
mkdirSync(folder,{recursive:true});
const shots=[
  {source:1,crop:[113,355,261,222],title:"选肉与切块",label:"切块均匀",
    narration:"做红烧肉，选带皮、肥瘦相间的五花肉，切成大小均匀的方块。每块大约两到三厘米，别切得太碎，这样炖好以后更容易保持形状。"},
  {source:1,crop:[404,188,253,367],title:"冷水焯肉，撇去浮沫",label:"冷水下锅",
    narration:"切好的肉冷水下锅，逐渐加热，水开以后撇去浮沫。焯好后捞出来，用温水冲净表面，再沥干水分，避免下锅时油花飞溅。"},
  {source:2,crop:[113,260,192,236],title:"糖色第一步：小火化糖",label:"小火化糖",
    narration:"锅里放少量油和冰糖，先用小火慢慢加热，让糖逐渐融化。这个阶段不要急着追求颜色，更不要开大火，否则糖还没化匀就可能烧焦。"},
  {source:2,crop:[297,325,182,199],title:"糖色第二步：观察变色",label:"观察变色",
    narration:"糖融化后，继续用小火加热，观察糖浆由浅黄逐渐变成琥珀色。颜色变化很快，要一直盯着锅里的状态，不要在这时候离开灶台。"},
  {source:2,crop:[480,263,174,231],title:"糖色第三步：及时下肉",label:"及时下肉",
    narration:"糖色接近红褐色时，及时放入沥干的肉块，翻拌上色。不要等到糖浆发黑、冒烟才下肉，烧焦的苦味很难靠后面的调味补回来。"},
  {source:3,crop:[112,138,544,493],title:"加水调味，小火慢炖",label:"小火慢炖",
    narration:"肉块上色后，加热水、姜片和适量调料，水量基本没过肉。烧开后转小火，保持轻微沸腾，不要让整锅汤汁持续猛烈翻滚。"},
  {source:3,crop:[112,138,544,493],title:"炖到软糯，再准备收汁",label:"筷子试软",
    narration:"炖煮通常需要一到一个半小时，具体看肉块大小和火力。用筷子试一试，能够比较轻松地插入肉块，再进入下一步，不要只看钟表。"},
  {source:4,title:"收汁对照：从稀汤到浓汁",label:"翻动防糊",
    leftNarration:"先看左边，肉已经炖软，但汤汁还是稀的。打开锅盖，适当加大火力，让多余的水分蒸发。",
    rightNarration:"再看右边，浓汁已经包裹在肉块表面。这个阶段要经常翻动，防止锅底粘住。汤汁能够挂在肉上就关火，不要烧到完全干锅。"},
  {source:5,title:"出锅：红亮软糯的红烧肉",label:"趁热上桌",
    narration:"最后盛出红烧肉，肉块表面裹着一层红亮的浓汁。选肉切块、冷水焯水、小火炒糖、慢炖到软，再翻动收汁，按步骤做就更稳妥。"},
];
const scenes=[];
for(const [index,shot] of shots.entries()) {
  shot.narration??=shot.leftNarration+shot.rightNarration;
  const original=resolve(root,`image/braised-pork-recovery/scene_${shot.source}-clean.png`);
  const provenance=JSON.parse(readFileSync(resolve(root,`image/braised-pork-recovery/scene_${shot.source}-clean.json`),"utf8"));
  assert(provenance.ok);
  let image=sharp(original);
  if(shot.crop) {const [left,top,width,height]=shot.crop;image=image.extract({left,top,width,height});}
  const asset=resolve(folder,`shot_${index}.png`);
  await image.png().toFile(asset);
  assert(shot.narration.length>=45);
  const regions=shot.leftNarration?[
    {id:"thin",sequence:1,subtitle:shot.leftNarration,region:{x:0,y:0,width:480,height:540},reveal:{startMs:0,durationMs:6000},source:"authored"},
    {id:"thick",sequence:2,subtitle:shot.rightNarration,region:{x:480,y:0,width:480,height:540},reveal:{startMs:6000,durationMs:5500},source:"authored"},
  ]:[];
  scenes.push({id:`shot_${index}`,order:index,title:shot.title,narration:shot.narration,
    duration_estimate:12,animations:[],reference_image_path:asset,
    image_description:provenance.prompt,visual_anchor:shot.title,
    visual_beats:[{id:"subject",narration:shot.narration,draw_intent:shot.title,required_labels:[shot.label],duration_estimate:12}],
    annotation_plan:[{type:"side_label",label:shot.label,target:shot.title,beat_id:"subject",layer:"renderer"}],
    canvasWidth:960,canvasHeight:540,renderElements:regions,
    board_mode:"whiteboard",hand_usage:"trace",render_strategy:"hybrid",video_style:"whiteboard",visual_style:"teacher_whiteboard",pen_style:"marker",
    source_artwork:original,source_model:"local FLUX",source_crop:shot.crop??null,
  });
}
const payload={storyboard:{topic:"红烧肉制作（逐镜配图同步版）",video_style:"whiteboard",image_generation_mode:"flux",pen_style:"marker",total_duration_estimate:scenes.length*12,scenes},subtitlesEnabled:true,forceRender:true};
writeFileSync(resolve(folder,"render-request.json"),JSON.stringify(payload,null,2));
const response=await fetch("http://localhost:3002/render",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
assert(response.ok,await response.clone().text());
const job=await response.json();
writeFileSync(resolve(folder,"render-job.json"),JSON.stringify(job,null,2));
console.log(JSON.stringify(job));

// A new lesson on the verified continuous-audio whiteboard renderer.
import assert from "node:assert/strict";
import {readFileSync, writeFileSync} from "node:fs";
import {resolve} from "node:path";
import {continuousNarration} from "./continuous-narration.mjs";
import {upgradeScenesWithGlyphOutlines} from "./glyph.mjs";
import {writeGeneratedProject} from "./codegen.mjs";
import {bundleAndRender} from "./render-core.mjs";

const jobId = "sugar-harms-handdraw-v2";
const lessons = [
  {title:"多吃糖的坏处：先分清是哪种糖", rows:[
    ["cube","糖不是碰一点就有害。"],
    ["drink","要警惕长期过量摄入游离糖。"],
    ["honey","甜饮料、甜点、蜂蜜和果汁都要留意。"],
    ["fruit","完整水果不必和甜饮料一概而论。"],
  ]},
  {title:"坏处一：增加蛀牙风险", rows:[
    ["tooth","口腔细菌会利用糖产生酸。"],
    ["crack","酸会损伤牙齿表面的牙釉质。"],
    ["clock","频繁吃甜食会增加牙齿受酸侵袭的机会。"],
    ["brush","少吃糖和使用含氟牙膏都很重要。"],
  ]},
  {title:"坏处二：更容易摄入过多热量", rows:[
    ["drink","甜饮料能在不知不觉中增加热量。"],
    ["stomach","液体热量通常不如固体食物让人饱。"],
    ["scale","长期摄入热量超过消耗就容易增重。"],
    ["balance","关键是总量和习惯而不是偶尔一口甜。"],
  ]},
  {title:"坏处三：长期代谢风险值得留意", rows:[
    ["liver","长期过量摄入游离糖不利于代谢健康。"],
    ["drink","经常喝含糖饮料与二型糖尿病风险升高有关。"],
    ["shield","但吃一块糖不等于一定得糖尿病。"],
    ["balance","体重、运动和整体饮食都很重要。"],
  ]},
  {title:"一瓶饮料：算算你喝了多少糖", rows:[
    ["label","假设饮料每一百毫升含糖十克。"],
    ["drink","喝完五百毫升就是五十克糖。"],
    ["spoon","以每天两千千卡为例游离糖应少于五十克。"],
    ["spoon","进一步降到二十五克以下可能更有益。"],
  ]},
  {title:"今天就能做：少喝甜饮料", rows:[
    ["water","先把一杯甜饮料换成白水或无糖茶。"],
    ["label","买饮料时查看营养表并注意整瓶容量。"],
    ["fruit","想吃甜的可以优先选择完整水果。"],
    ["steps","逐步减少甜度比追求完全无糖更容易坚持。"],
  ]},
];
const storyboard = await continuousNarration({topic:"多吃糖的坏处", scenes:lessons.map((lesson,i)=>({
  id:`sugar_${i}`,title:lesson.title,narration:lesson.rows.map(row=>row[1]).join(""),
}))});

const line = (...points) => points.map(([x,y])=>({x,y}));
const box = (x,y,w,h) => line([x,y],[x+w,y],[x+w,y+h],[x,y+h],[x,y]);
const circle = (x,y,r) => Array.from({length:41},(_,i)=>({x:x+r*Math.cos(i*Math.PI/20),y:y+r*Math.sin(i*Math.PI/20)}));
const arrow = () => [line([4,43],[22,29],[34,31],[51,9]),line([39,9],[51,9],[50,21])];
const bottle = () => [box(23,1,16,8),line([23,9],[23,17],[13,26],[13,57],[49,57],[49,26],[39,17],[39,9]),line([14,33],[48,33]),line([14,48],[48,48])];
const tooth = () => [line([30,12],[20,5],[9,7],[4,18],[8,34],[12,55],[20,57],[25,37],[30,32],[35,37],[40,57],[48,55],[53,34],[57,18],[52,7],[41,5],[30,12])];
function icon(name) {
  switch(name) {
    case "cube": return [box(7,18,33,33),line([7,18],[21,6],[54,6],[40,18]),line([40,51],[54,39],[54,6])];
    case "drink": return bottle();
    case "water": return [line([9,9],[16,54],[47,54],[54,9]),line([14,30],[25,27],[36,31],[50,29]),line([30,1],[25,10],[30,15],[35,10],[30,1])];
    case "honey": return [box(13,23,38,31),box(10,15,44,8),line([23,15],[23,6],[42,2]),line([20,36],[43,36]),line([20,43],[38,43])];
    case "fruit": return [line([31,19],[19,12],[8,16],[3,29],[9,47],[20,57],[31,53],[42,57],[54,46],[59,28],[52,15],[42,12],[31,19]),line([31,19],[30,7],[38,2]),line([32,9],[43,4],[51,8],[43,14],[32,9])];
    case "tooth": return [...tooth(),circle(12,21,3),circle(44,20,3),line([22,22],[30,27],[38,22])];
    case "crack": return [...tooth(),line([34,9],[26,23],[34,30],[27,39])];
    case "clock": return [circle(30,30,26),line([30,10],[30,30],[45,36]),line([3,7],[12,2]),line([48,2],[58,9])];
    case "brush": return [line([5,50],[37,18],[43,24],[11,56],[5,50]),line([35,20],[45,10],[52,17],[42,27]),line([43,12],[51,4]),line([47,15],[56,7]),line([50,18],[59,10])];
    case "stomach": return [line([23,2],[23,18],[13,22],[9,33],[12,45],[23,55],[39,57],[51,48],[56,33],[51,21],[39,18],[35,8],[35,2]),line([20,33],[28,29],[40,33],[47,30])];
    case "scale": return [box(6,8,50,48),line([13,17],[19,29],[41,29],[49,17],[13,17]),line([31,27],[38,16]),line([19,44],[43,44])];
    case "balance": return [line([31,4],[31,53]),line([6,53],[55,53]),line([6,18],[56,18]),line([14,18],[5,38],[25,38],[14,18]),line([47,18],[37,38],[57,38],[47,18]),circle(31,15,4)];
    case "liver": return [line([4,21],[18,11],[35,9],[55,15],[57,27],[45,37],[35,37],[25,51],[12,45],[5,34],[4,21]),line([35,9],[32,27],[35,37])];
    case "shield": return [line([30,3],[54,13],[51,36],[42,48],[30,58],[17,48],[9,35],[6,13],[30,3]),line([18,30],[27,39],[44,21])];
    case "label": return [box(7,3,47,55),line([15,15],[46,15]),line([15,26],[46,26]),line([15,37],[46,37]),line([15,48],[46,48]),line([33,15],[33,48])];
    case "spoon": return [circle(18,18,12),line([26,27],[51,53],[56,48],[30,23]),line([2,54],[15,46],[27,54],[2,54])];
    case "steps": return [line([3,56],[18,56],[18,40],[34,40],[34,24],[50,24],[50,8],[60,8]),...arrow()];
    default: throw new Error(`No drawing for ${name}`);
  }
}

const INK = "#292B32", GREEN = "#39856E", RED = "#D16B53", GOLD = "#D1A13F";
const at = (paths,x,y,scale=1,color=INK,width=3) => paths.map(points=>({points:points.map(p=>({x:x+p.x*scale,y:y+p.y*scale})),color,width}));
const connect = (x,y,length=75,color=GREEN) => at([line([0,0],[length,0]),line([length-12,-8],[length,0],[length-12,8])],x,y,1,color);
const drop = () => [line([22,0],[6,25],[2,36],[5,47],[15,53],[27,52],[37,44],[39,32],[22,0])];
const person = () => [circle(30,12,11),line([30,23],[30,55]),line([10,37],[30,29],[50,37]),line([30,55],[14,76]),line([30,55],[46,76])];
const cake = () => [line([2,19],[33,4],[59,19],[2,19],[2,49],[59,49],[59,19]),line([2,34],[59,34]),line([12,19],[12,24],[20,27],[26,22],[34,27],[44,22],[51,25],[59,21])];
const bacteria = () => [circle(18,18,12),...Array.from({length:8},(_,i)=>{
  const a=i*Math.PI/4;return line([18+13*Math.cos(a),18+13*Math.sin(a)],[18+19*Math.cos(a),18+19*Math.sin(a)]);
}),circle(14,15,1),circle(22,15,1),line([13,22],[23,22])];
const run = () => [circle(36,8,7),line([33,17],[25,35],[39,44],[49,61]),line([25,35],[15,48],[2,49]),line([30,23],[13,21],[6,31]),line([30,23],[45,29],[54,19])];
const plate = () => [circle(30,30,27),circle(30,30,20),line([29,11],[29,49]),line([29,30],[48,30])];
const cross = (x,y,w=55) => at([line([0,0],[w,w]),line([w,0],[0,w])],x,y,1,RED,4);

// Each step adds relevant geometry to one evolving board, not another sentence.
function drawing(scene,cue) {
  const p = (name,x,y,s=1,c=INK) => at(icon(name),x,y,s,c);
  if(scene===0) return [
    [...p("cube",88,160,2.3),...at([circle(32,32,42)],90,150,2,GREEN)],
    [...p("drink",345,125,2.8),...p("cube",520,210,1.1,GOLD),...p("cube",570,250,1.1,GOLD),...connect(254,233)],
    [...p("honey",345,305,1.2,GOLD),...at(cake(),450,315,1.2),...p("drink",557,315,1.2,RED)],
    [...p("fruit",738,160,2.7,GREEN),...at([line([0,20],[15,35],[47,0])],775,340,1,GREEN,4)],
  ][cue];
  if(scene===1) return [
    [...at(tooth(),355,112,4.2),...p("cube",100,150,1.2,GOLD),...at(bacteria(),150,260,1.3,RED),...connect(225,230,95,RED)],
    [...at(drop(),420,155,1,RED),...at([line([34,9],[26,23],[34,30],[27,39])],355,112,4.2,RED,4)],
    [...p("clock",710,120,1.8,RED),...p("cube",700,258,.8,GOLD),...p("cube",760,300,.8,GOLD),...p("cube",820,260,.8,GOLD),...connect(684,336,-65,RED)],
    [...p("brush",700,280,2,GREEN),...cross(104,160,64),...at([line([0,12],[11,23],[35,0])],568,345,1,GREEN,4)],
  ][cue];
  if(scene===2) return [
    [...p("drink",80,120,3),...p("cube",240,260,.9,GOLD),...p("cube",275,315,.9,GOLD)],
    [...p("stomach",365,130,3),...connect(270,220,80),...at([line([0,0],[45,0]),line([0,10],[45,10])],435,268,1,GOLD)],
    [...p("scale",690,130,3),...connect(575,220,87,RED),...at(arrow(),760,310,1,RED)],
    [...at(plate(),375,300,1.3,GREEN),...at(run(),525,310,1.1,GREEN),...at([line([0,0],[0,48]),line([0,48],[500,48]),line([500,48],[500,0])],180,330,1,GREEN)],
  ][cue];
  if(scene===3) return [
    [...p("liver",80,145,3.5),...at(drop(),270,265,.8,GOLD)],
    [...p("drink",380,130,2.8),...connect(295,224,70,RED),...at([line([0,50],[18,30],[36,35],[57,5]),line([43,5],[57,5],[57,19])],560,170,1.7,RED)],
    [...p("cube",560,315,1),...at([line([0,0],[55,0]),line([0,15],[55,15]),line([10,32],[47,-15])],650,335,1,RED),...p("shield",765,300,1.2,GREEN)],
    [...at(person(),760,130,1.7,GREEN),...at(run(),695,235,.8,GREEN),...at(plate(),830,220,.8,GREEN)],
  ][cue];
  if(scene===4) return [
    [...p("label",75,130,3.5),...at([box(0,0,68,16)],119,215,1,GOLD,5)],
    [...p("drink",350,125,3.2),...connect(270,220,58),...connect(550,220,45),...Array.from({length:10},(_,i)=>p("cube",630+(i%5)*48,160+Math.floor(i/5)*63,.8,GOLD)).flat()],
    [...at(plate(),105,325,.9,GREEN),...at([line([0,0],[0,43],[240,43]),line([5,8],[195,8]),line([195,0],[195,43])],285,305,1,GOLD)],
    [...at([line([0,0],[0,43],[220,43]),line([5,23],[100,23]),line([100,7],[100,43]),line([178,2],[198,19],[227,-8])],615,305,1,GREEN)],
  ][cue];
  return [
    [...p("drink",70,135,2.6),...connect(258,220,75),...p("water",370,138,2.7,GREEN),...cross(102,212,73)],
    [...p("label",700,130,2.6),...at([circle(0,0,41),line([29,29],[63,63])],800,202,1,GOLD)],
    [...p("fruit",580,295,1.5,GREEN),...at(plate(),737,300,1.3,GREEN)],
    [...p("steps",80,297,1.7,GREEN),...p("water",235,325,.65,GREEN),...p("water",300,325,.65,GREEN),...p("water",365,325,.65,GREEN)],
  ][cue];
}
const captions = [
  [["不是禁糖",87,110],["游离糖",373,104],null,["完整水果",736,110]],
  [["细菌＋糖",95,112],["产酸",480,126],["频繁吃甜",695,104],null],
  [["额外热量",90,102],["饱腹感弱",365,105],["长期增重",690,105],null],
  [["代谢健康",91,111],["风险增加",525,115],["不等于必然生病",580,373],["整体习惯",754,104]],
  [["10g / 100mL",78,108],["500mL = 50g",606,110],["2000kcal：少于50g",271,371],["少于25g",680,371]],
  [["改喝白水",200,106],["看标签",706,107],["完整水果",600,272],["逐步减糖",90,269]],
];

const scenes = storyboard.scenes.map((spoken,index)=>{
  const lesson = lessons[index];
  assert.deepEqual(spoken.subtitleCues.map(cue=>cue.text), lesson.rows.map(row=>row[1]));
  const scene = {...spoken, duration:spoken.timingPlan.durationFrames, boardMode:"whiteboard",videoStyle:"whiteboard",
    visualStyle:"teacher_whiteboard",handUsage:"trace",accent:"#39856E",transitionFrames:0,
    drawOps:[],texts:[],strokes:[],glyphPaths:[],renderElements:[],summaryPoints:[],keywords:[],rasterReveal:null};
  spoken.subtitleCues.forEach((cue,row)=>{
    const paths = drawing(index,row);
    const caption = captions[index][row];
    const split = caption ? cue.startFrame + (cue.endFrame-cue.startFrame)*.92 : cue.endFrame;
    const weights = paths.map(path=>path.points.slice(1).reduce((sum,p,k)=>sum+Math.hypot(p.x-path.points[k].x,p.y-path.points[k].y),0));
    const total = weights.reduce((a,b)=>a+b,0);
    let cursor = cue.startFrame;
    paths.forEach(({points,color,width},j)=>{
      const id = `s${index}_cue_${row}_shape_${j}`;
      const startFrame = cursor;
      const endFrame = j===paths.length-1 ? split : cursor+(split-cue.startFrame)*weights[j]/total;
      cursor = endFrame;
      scene.drawOps.push({id,kind:"path",startFrame,endFrame,points,beatId:`cue_${row}`});
      const length = points.slice(1).reduce((sum,p,k)=>sum+Math.hypot(p.x-points[k].x,p.y-points[k].y),0);
      scene.strokes.push({opId:id,role:"semantic",d:points.map((p,k)=>`${k?"L":"M"} ${p.x} ${p.y}`).join(" "),
        color,strokeWidth:width,dashLength:length});
    });
    if(caption) {
      const id = `s${index}_cue_${row}_text`;
      scene.drawOps.push({id,kind:"text",startFrame:split,endFrame:cue.endFrame,points:[],beatId:`cue_${row}`});
      const [text,x,y] = caption;
      scene.texts.push({opId:id,text,x,y,fontSize:21,maxWidth:320,color:GREEN});
    }
  });
  assert(scene.texts.reduce((sum,text)=>sum+text.text.length,0)<=48,"Too much board text");
  return scene;
});
const outlined = upgradeScenesWithGlyphOutlines(scenes).scenes;
for (const scene of outlined) {
  assert(scene.drawOps.flatMap(op=>op.points).every(p=>p.x>=40 && p.x<=920 && p.y>=95 && p.y<398),"Drawing/text overlaps an overlay or safe area");
  assert.equal(scene.subtitleCues.map(cue=>cue.text).join(""),scene.narration);
  for (const [i,cue] of scene.subtitleCues.entries()) {
    const ops = scene.drawOps.filter(op=>op.beatId===`cue_${i}`);
    assert(ops.length>1 && ops.every(op=>op.startFrame>=cue.startFrame-.02 && op.endFrame<=cue.endFrame+.2));
    const drawingTime = ops.filter(op=>op.kind==="path").reduce((sum,op)=>sum+op.endFrame-op.startFrame,0);
    assert(drawingTime/(cue.endFrame-cue.startFrame)>=.9,"Drawing must dominate each spoken cue");
    for(let frame=cue.startFrame;frame<cue.endFrame;frame++) {
      assert(ops.some(op=>op.startFrame<=frame && op.endFrame>frame),`Unillustrated spoken frame ${frame}`);
    }
  }
}
const templateFile = readFileSync("../../services/api/src/planner/fallback/_tsx_template_string.py","utf8");
const template = templateFile.slice(templateFile.indexOf("import React"),templateFile.lastIndexOf("'''"))
  .replace("__SCENES_JSON__",JSON.stringify(outlined)).replaceAll("__VIDEO_WIDTH__","960").replaceAll("__VIDEO_HEIGHT__","540")
  .replaceAll("__BACKGROUND_MUSIC_URL__","null").replaceAll("__BACKGROUND_MUSIC_VOLUME__","0.12").replaceAll("__SUBTITLES_ENABLED__","true");
const generated = {tsx:template,width:960,height:540,fps:24,durationInFrames:scenes.reduce((sum,s)=>sum+s.duration,0)};
const {entryPath} = writeGeneratedProject(jobId,generated,storyboard,{subtitlesEnabled:true});
const output = resolve("../../outputs/sugar-harms-handdraw-v2.mp4");
await bundleAndRender(jobId,entryPath,output);
writeFileSync(resolve("../../outputs/sugar-harms-handdraw-v2-script.json"),JSON.stringify({
  topic:"多吃糖的坏处",sources:[
    "https://www.who.int/news/item/04-03-2015-who-calls-on-countries-to-reduce-sugars-intake-among-adults-and-children",
    "https://www.who.int/news-room/fact-sheets/detail/healthy-diet",
  ],durationSeconds:generated.durationInFrames/24,scenes:outlined.map(s=>({title:s.title,narration:s.narration,subtitleCues:s.subtitleCues})),
},null,2));
console.log(JSON.stringify({output,durationSeconds:generated.durationInFrames/24,scenes:scenes.length}));

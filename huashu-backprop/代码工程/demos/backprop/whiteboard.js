// 反向传播算法白板解说（RSA Animate 型，30 秒，7 镜）
// 语法卡：y3_whiteboard.md
// 一整块大白板，相机从左到右横向跟随论证移动，收尾拉远看全图
(() => {
const W = 1920, H = 1080;
const INK   = '#0A0503';
const OGE   = '#EF7226';
const BOARD = '#FBFBFB';
const LW    = 6.5;
const SPEED = 2600;

// 世界 X 锚点（各块中心）
const CY = 540;
const X1 = 960, X2 = 3200, X3 = 5600, X4 = 8200, X5 = 10800, X6 = 13400;
const X_FULL = 7200;   // 收尾全图中心

// ── 相机关键帧 ──────────────────────────────────────────────────────────────
const camAt = t => CAM.at([
  { t: 0,    x: X1,     y: CY, z: 1.0 },
  { t: 2.2,  x: X1,     y: CY, z: 1.0 },
  { t: 3.0,  x: X2,     y: CY, z: 1.0, ease: MO.sineInOut },
  { t: 6.2,  x: X2,     y: CY, z: 1.0 },
  { t: 7.0,  x: X3,     y: CY, z: 1.0, ease: MO.sineInOut },
  { t: 11.2, x: X3,     y: CY, z: 1.0 },
  { t: 12.0, x: X4,     y: CY, z: 1.0, ease: MO.sineInOut },
  { t: 16.2, x: X4,     y: CY, z: 1.0 },
  { t: 17.0, x: X5,     y: CY, z: 1.0, ease: MO.sineInOut },
  { t: 21.2, x: X5,     y: CY, z: 1.0 },
  { t: 22.0, x: X6,     y: CY, z: 1.0, ease: MO.sineInOut },
  { t: 26.2, x: X6,     y: CY, z: 1.0 },
  { t: 27.5, x: X_FULL, y: CY, z: 0.22, ease: MO.sineInOut },
  { t: 30.0, x: X_FULL, y: CY, z: 0.22 },
], t);

// ── 笔画时间线 ───────────────────────────────────────────────────────────────
const B = DG.board({ ink: INK, lw: LW, speed: SPEED, font: '"LXGWWenKai-500"' });

// ════ 第 1 镜（0–3s）桌面、试卷、零分 ════
B.at(0.2);
B.line([[X1-400, 720],[X1+400, 720]], { w: 4, speed: SPEED * 2 });
for (let i = 2; i >= 0; i--) {
  const bx = X1 + 80 + i * 18, by = 430 - i * 18;
  B.line([[bx, by],[bx+260,by],[bx+260,by+190],[bx,by+190],[bx,by+3]], { w: 5, speed: SPEED * 4, amp: 0 });
}
B.text('0分', X1 + 190, 530, 100, { col: OGE, rate: 7.5 });
B.line([[X1-180, 610],[X1+70, 545]], { col: OGE, speed: SPEED * 1.5 });
B.line([[X1+40, 517],[X1+74, 545],[X1+44, 571]], { col: OGE, smooth: false });
B.text('哪里出错了？', X1-80, 820, 72, { align: 'center' });
B.at(2.4);
B.line([[X1+550, 540],[X1+980, 540]], { col: OGE, speed: SPEED * 1.8 });
B.line([[X1+950, 512],[X1+984, 540],[X1+950, 568]], { col: OGE, smooth: false });

// ════ 第 2 镜（3–7s）三层神经网络 ════
B.at(3.1);
const NX = [X2 - 420, X2 - 100, X2 + 280];
const NY = [[250, 450, 650], [200, 350, 500, 650], [350, 550]];
for (let l = 0; l < 2; l++)
  for (const ya of NY[l])
    for (const yb of NY[l + 1])
      B.segment([NX[l] + 28, ya], [NX[l + 1] - 28, yb], { w: 2, speed: SPEED * 3 });
B.at(B.cur + 0.1);
for (let l = 0; l < 3; l++)
  for (const y of NY[l])
    B.line(DG.arcPts(NX[l], y, 28, 28, 0, Math.PI * 2, 18), { w: LW, speed: SPEED * 4, amp: 0.6, gap: 0.01 });
B.at(B.cur + 0.05);
for (const [l, label] of [[0,'输入层'],[1,'隐藏层'],[2,'输出层']])
  B.text(label, NX[l], NY[l][NY[l].length - 1] + 80, 52, { align: 'center' });
B.text('神经网络', X2, 130, 78, { align: 'center', col: OGE });
B.at(6.3);
B.line([[X2+520,420],[X2+980,420]], { col: OGE, speed: SPEED * 1.8 });
B.line([[X2+950,392],[X2+984,420],[X2+950,448]], { col: OGE, smooth: false });

// ════ 第 3 镜（7–12s）误差、红箭头向左 ════
B.at(7.1);
const OX = X3 - 280;
for (const y of [350, 550])
  B.line(DG.arcPts(OX, y, 32, 32, 0, Math.PI * 2, 18), { w: LW, speed: SPEED * 4, amp: 0.4, gap: 0.01 });
B.line([[X3+80,300],[X3+280,300],[X3+280,420],[X3+80,420],[X3+80,303]], { w: 5, speed: SPEED * 3, amp: 0 });
B.text('正确答案', X3+180, 375, 48, { align: 'center' });
B.line([[OX+40,450],[X3+70,450]], { w: 5, speed: SPEED * 1.5 });
B.text('= 误差', X3+90, 460, 60, { col: OGE });
B.at(B.cur + 0.3);
B.line([[X3+60,540],[X3-400,540]], { col: OGE, speed: SPEED * 1.2 });
B.line([[X3-370,512],[X3-404,540],[X3-370,568]], { col: OGE, smooth: false });
B.text('反向传播', X3-80, 620, 64, { align: 'center', col: OGE });
B.at(11.3);
B.line([[X3+700,440],[X3+980,440]], { col: OGE, speed: SPEED * 1.8 });
B.line([[X3+950,412],[X3+984,440],[X3+950,468]], { col: OGE, smooth: false });

// ════ 第 4 镜（12–17s）梯度逐层反流 ════
B.at(12.1);
const BNX = [X4 - 500, X4 - 100, X4 + 300];
for (let l = 0; l < 2; l++)
  for (const ya of [300, 500])
    for (const yb of [250, 450, 650])
      B.segment([BNX[l] + 24, ya], [BNX[l + 1] - 24, yb], { w: 2, speed: SPEED * 3.5 });
for (let l = 0; l < 3; l++)
  for (const y of (l === 1 ? [250, 450, 650] : [300, 500]))
    B.line(DG.arcPts(BNX[l], y, 24, 24, 0, Math.PI * 2, 16), { w: LW, speed: SPEED * 5, amp: 0.4, gap: 0.01 });
B.at(B.cur + 0.2);
for (const ay of [250, 450, 650]) {
  B.at(B.cur + 0.15);
  B.line([[BNX[2]-30, ay],[BNX[1]+30, ay]], { col: OGE, speed: SPEED * 0.9 });
  B.line([[BNX[1]+60, ay-28],[BNX[1]+26, ay],[BNX[1]+60, ay+28]], { col: OGE, smooth: false });
  B.at(B.cur + 0.12);
  B.line([[BNX[1]-30, ay],[BNX[0]+30, ay]], { col: OGE, speed: SPEED * 0.9 });
  B.line([[BNX[0]+60, ay-28],[BNX[0]+26, ay],[BNX[0]+60, ay+28]], { col: OGE, smooth: false });
}
B.text('梯度反流', X4+20, 790, 64, { align: 'center', col: OGE });
B.at(16.2);
B.line([[X4+680,440],[X4+980,440]], { col: OGE, speed: SPEED * 1.8 });
B.line([[X4+950,412],[X4+984,440],[X4+950,468]], { col: OGE, smooth: false });

// ════ 第 5 镜（17–22s）权重更新 ════
B.at(17.1);
const WY = 450;
B.line([[X5-360,WY],[X5+360,WY]], { w: 8, speed: SPEED * 1.2 });
B.text('w = 0.82', X5, WY-80, 72, { align: 'center' });
B.at(B.cur + 0.1);
B.line([[X5-180,WY-80],[X5+180,WY-80]], { w: 5, col: OGE, speed: SPEED * 2 });
B.at(B.cur + 0.15);
B.text('w = 0.61', X5, WY+80, 80, { align: 'center', col: OGE });
B.line([[X5,WY-30],[X5,WY+30]], { w: 6, col: OGE, speed: SPEED * 2 });
B.line([[X5-24,WY+4],[X5,WY+32],[X5+24,WY+4]], { col: OGE, smooth: false });
B.text('权重更新', X5, 720, 64, { align: 'center' });
B.at(21.2);
B.line([[X5+600,440],[X5+980,440]], { col: OGE, speed: SPEED * 1.8 });
B.line([[X5+950,412],[X5+984,440],[X5+950,468]], { col: OGE, smooth: false });

// ════ 第 6 镜（22–27s）试卷分数变高 ════
B.at(22.1);
for (let i = 2; i >= 0; i--) {
  const bx = X6 + 80 + i * 18, by = 420 - i * 18;
  B.line([[bx, by],[bx+260,by],[bx+260,by+190],[bx,by+190],[bx,by+3]], { w: 5, speed: SPEED * 4, amp: 0 });
}
B.text('0→', X6+100, 520, 72, {});
B.text('98分', X6+220, 520, 100, { col: OGE, rate: 7.5 });
B.at(B.cur + 0.2);
B.line([[X6-280,500],[X6-180,580],[X6+40,360]], { col: OGE, w: 8, smooth: false });
B.text('训练完成', X6-40, 720, 72, { align: 'center' });

// ════ 第 7 镜（27–30s）拉远看全图 ════
B.at(27.2);
B.text('反向传播', X_FULL, 80, 160, { align: 'center', col: OGE, rate: 7.5 });

// ── draw 函数（全段共用，全局时间 t 传入）────────────────────────────────────
const shot = (c, lt, t) => {
  const cam = camAt(t);
  c.fillStyle = BOARD;
  c.fillRect(0, 0, W, H);
  c.save();
  CAM.apply(c, cam);
  const r = B.draw(c, t);
  c.restore();
  if (r && r.tip) {
    const [hx, hy] = B.penAt(t, cam, r.tip);
    DG.pen(c, hx, hy, r.col || B.penColor(t), Math.sin(t * 7) * 0.03);
  }
};

// ── 注册（scenes/index.js 按 SCENES[id].draw 查找）───────────────────────────
window.SCENES = window.SCENES || {};
for (const id of ['bp_s1','bp_s2','bp_s3','bp_s4','bp_s5','bp_s6','bp_s7'])
  window.SCENES[id] = { draw: shot };
})();

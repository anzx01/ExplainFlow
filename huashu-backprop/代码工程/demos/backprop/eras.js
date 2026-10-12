// 反向传播算法白板解说（RSA Animate 型，30 秒，7 镜）
// 预览：index.html?film=demos/backprop
// 渲染：render.py --film demos/backprop --out backprop.mp4
window.PUNCH = 0;
window.SCENE_LIBS = ['demos/backprop/whiteboard.js'];
window.ERAS = [
  { id: 'bp_s1', dur: 3.0 },                                                        // 一双手翻开试卷，指着零分
  { id: 'bp_s2', dur: 4.0, transition: { type: 'same', dur: 0.85 } },               // 画三层神经网络
  { id: 'bp_s3', dur: 5.0, transition: { type: 'same', dur: 0.85 } },               // 画输出误差，红箭头向左
  { id: 'bp_s4', dur: 5.0, transition: { type: 'same', dur: 0.80 } },               // 红箭头反向传播穿层
  { id: 'bp_s5', dur: 5.0, transition: { type: 'same', dur: 0.80 } },               // 权重数字更新变化
  { id: 'bp_s6', dur: 5.0, transition: { type: 'same', dur: 0.80 } },               // 试卷分数变高
  { id: 'bp_s7', dur: 3.0, transition: { type: 'same', dur: 1.20 } },               // 拉远看全图
];

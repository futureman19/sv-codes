/* scanner.js — webcam scanner UI: camera -> decoder.js -> verified action card. */
"use strict";
(function(){
const S = SVC, D = SVDec;

const ACTION_NAMES = {
  0x0000:"NOP", 0x0001:"HALT", 0x0002:"REPORT_STATUS",
  0x00A1:"MOVE_TO", 0x00A2:"MOVE_VECTOR", 0x00B1:"CLAIM_BOUNTY",
  0x00C1:"SET_CONFIG", 0x00FF:"VENDOR",
};

function boot(){
  const btn = document.getElementById("camStart");
  if (!btn) return;
  const video = document.getElementById("camVideo");
  const canvas = document.getElementById("camCanvas");
  const statusEl = document.getElementById("scanStatus");
  const card = document.getElementById("scanResult");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const scanner = new D.StreamScanner(SVEnc.GOLDEN_PUB_HEX);
  let running = false, lastReport = "";

  btn.addEventListener("click", async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 } }, audio: false });
      video.srcObject = stream;
      await video.play();
      running = true;
      btn.style.display = "none";
      statusEl.textContent = "scanning… point the camera at an SV Code grid";
      loop();
    } catch (e) {
      statusEl.textContent = "camera unavailable: " + e.message;
    }
  });

  function loop(){
    if (!running) return;
    if (video.readyState >= 2){
      const vw = video.videoWidth, vh = video.videoHeight;
      const scale = Math.min(1, 960 / vw);
      canvas.width = Math.round(vw * scale); canvas.height = Math.round(vh * scale);
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const anchors = D.findAnchors(img.data, img.width, img.height);
      if (anchors){
        // overlay quad
        ctx.strokeStyle = "#22d3ee"; ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(anchors[0][0], anchors[0][1]);
        ctx.lineTo(anchors[1][0], anchors[1][1]);
        ctx.lineTo(anchors[3][0], anchors[3][1]);
        ctx.lineTo(anchors[2][0], anchors[2][1]);
        ctx.closePath(); ctx.stroke();
        const bits = D.decodeImageData(img.data, img.width, img.height);
        if (bits){
          const res = scanner.feedBits(bits);
          const prog = scanner.progress();
          statusEl.textContent = res ? "decoded ✓"
            : prog ? `collecting… ${prog[0]}/${prog[1]} symbols (${scanner.framesSeen} frames)`
            : "grid found, reading…";
          if (res) showResult(res);
        }
      } else {
        statusEl.textContent = "searching for grid…";
      }
    }
    setTimeout(loop, 100);
  }

  function showResult(res){
    const env = res.env;
    const name = ACTION_NAMES[env.action] || ("0x" + env.action.toString(16).padStart(4, "0"));
    let payload = "";
    try { payload = new TextDecoder().decode(env.payload); } catch (e) { payload = "[" + env.payload.length + " bytes]"; }
    const sigBadge = res.sig === "valid" ? '<span class="sig ok">VALID ✓ test authority</span>'
      : res.sig === "demo" ? '<span class="sig demo">DEMO (zeroed sig)</span>'
      : res.sig === "invalid" ? '<span class="sig bad">INVALID ✗</span>'
      : '<span class="sig demo">unverified</span>';
    const html = `
      <div class="res-row"><span>ACTION</span><b>${name} (0x${env.action.toString(16).padStart(4,"0")})</b></div>
      <div class="res-row"><span>TARGET</span><b>0x${env.targetId.toString(16).padStart(8,"0")}</b></div>
      <div class="res-row"><span>SIGNATURE</span><b>${sigBadge}</b></div>
      ${payload ? `<div class="res-payload">${escapeHtml(payload)}</div>` : ""}`;
    if (html !== lastReport){ card.innerHTML = html; lastReport = html; }
    card.style.display = "block";
    if (res.sig === "invalid") card.classList.add("bad"); else card.classList.remove("bad");
  }
  function escapeHtml(s){ return s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
}
document.addEventListener("DOMContentLoaded", boot);
})();

/* scanner.js — webcam scanner UI: camera -> decoder.js -> verified action card. */
"use strict";
(function(){
const S = SVC, D = SVDec;

const ACTION_NAMES = {
  0x0000:"NOP", 0x0001:"HALT", 0x0002:"REPORT_STATUS",
  0x00A1:"MOVE_TO", 0x00A2:"MOVE_VECTOR", 0x00B1:"CLAIM_BOUNTY",
  0x00C1:"SET_CONFIG", 0x00FF:"VENDOR", 0xA47C:"COLLECTION_ITEM_CERT",
  0x17E9:"GAME_ITEM_CERT",
};

/* Known issuers: pubkey hex -> display label. Verification is against the
   envelope signature; the label just names the key that matched. */
const ISSUERS = {};
function registerIssuer(hex, label){ ISSUERS[hex.toLowerCase()] = label; }

function boot(){
  const btn = document.getElementById("camStart");
  if (!btn) return;
  const video = document.getElementById("camVideo");
  const canvas = document.getElementById("camCanvas");
  const statusEl = document.getElementById("scanStatus");
  const card = document.getElementById("scanResult");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  registerIssuer(SVEnc.GOLDEN_PUB_HEX, "test authority");
  registerIssuer("023a6f32a0528c1b02899c3dbd28cd055fa64ca626271578da4b4261076407a11d", "SV-GENESIS issuer");
  registerIssuer("038e2cb0ea841f2975ef15d762653ea481f6bc076bcb2683d21a8dc0bc5a486538", "Night Districts Studio (demo)");
  registerIssuer("031f179f4318ee0402cf66ff1f5d6eb07a8b341458b6e8c02c140a0f98cf810f0c", "Grydbound Armory (demo)");
  const scanner = new D.StreamScanner(Object.keys(ISSUERS));
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

  const VOTE_WINDOW = 9;                 // frames of per-cell majority vote
  let votes = [];                        // ring buffer of 2,704-bit frames
  let anchorMisses = 0, solved = false;

  function votedBits(){
    const n = votes.length, out = new Array(2704).fill(0);
    for (let i = 0; i < 2704; i++){
      let s = 0;
      for (let k = 0; k < n; k++) s += votes[k][i];
      out[i] = s * 2 > n ? 1 : 0;
    }
    return out;
  }

  function loop(){
    try {
      if (video.readyState >= 2){
        const vw = video.videoWidth, vh = video.videoHeight;
        const scale = Math.min(1, 960 / vw);
        canvas.width = Math.round(vw * scale); canvas.height = Math.round(vh * scale);
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const anchors = D.findAnchors(img.data, img.width, img.height);
        if (anchors){
          anchorMisses = 0;
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
            votes.push(bits);
            if (votes.length > VOTE_WINDOW) votes.shift();
            if (!solved){
              const res = scanner.feedBits(votedBits());
              const prog = scanner.progress();
              statusEl.textContent = res ? "decoded ✓"
                : prog ? `locking… ${prog[0]}/${prog[1]} symbols — hold steady`
                : `grid found, locking… (${votes.length} frames voted)`;
              if (res){ solved = true; showResult(res); }
            }
          }
        } else {
          anchorMisses++;
          if (anchorMisses > 12){          // ~1.2s of misses: genuinely lost
            votes.length = 0;
            statusEl.textContent = "searching for grid…";
          } else if (!solved){
            statusEl.textContent = "hold steady — re-acquiring…";
          }
        }
      }
    } catch (e) { /* a bad frame must never kill the scan loop */ }
    setTimeout(loop, 100);
  }

  function showResult(res){
    const env = res.env;
    const name = ACTION_NAMES[env.action] || ("0x" + env.action.toString(16).padStart(4, "0"));
    let payload = "";
    try { payload = new TextDecoder().decode(env.payload); } catch (e) { payload = "[" + env.payload.length + " bytes]"; }
    const sigBadge = res.sig === "valid"
        ? `<span class="sig ok">VALID ✓ ${escapeHtml(ISSUERS[(res.issuer||"").toLowerCase()] || "registered issuer")}</span>`
      : res.sig === "demo" ? '<span class="sig demo">DEMO (zeroed sig)</span>'
      : res.sig === "invalid" ? '<span class="sig bad">INVALID ✗ unknown issuer</span>'
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

  /* screenshot / file decode: no camera needed — same pipeline, one image */
  const pick = document.getElementById("imgPick");
  const pickBtn = document.getElementById("imgPickBtn");
  const pickStatus = document.getElementById("imgPickStatus");
  function decodeImageFile(file){
    if (!file) return;
    pickStatus.textContent = "reading…";
    const url = URL.createObjectURL(file);
    const im = new Image();
    im.onload = () => {
      const scale = Math.min(1, 1600 / Math.max(im.width, im.height));
      canvas.width = Math.round(im.width * scale);
      canvas.height = Math.round(im.height * scale);
      ctx.drawImage(im, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const bits = D.decodeImageData(img.data, img.width, img.height);
      if (!bits){ pickStatus.textContent = "no SV Code found in that image"; return; }
      const sc = new D.StreamScanner(Object.keys(ISSUERS));   // fresh: file decode is one-shot
      const res = sc.feedBits(bits);
      if (!res){ pickStatus.textContent = "grid read but stream incomplete — try a sharper shot"; return; }
      pickStatus.textContent = "decoded ✓";
      showResult(res);
      card.scrollIntoView({behavior: "smooth", block: "nearest"});
    };
    im.onerror = () => { pickStatus.textContent = "could not read that file"; };
    im.src = url;
  }
  if (pickBtn){
    pickBtn.addEventListener("click", () => pick.click());
    pick.addEventListener("change", () => decodeImageFile(pick.files[0]));
    const zone = document.querySelector(".scan-box");
    zone.addEventListener("dragover", e => { e.preventDefault(); });
    zone.addEventListener("drop", e => {
      e.preventDefault();
      if (e.dataTransfer.files && e.dataTransfer.files[0]) decodeImageFile(e.dataTransfer.files[0]);
    });
  }

  /* OS share sheet handoff: sw.js stashed the shared image in a cache */
  if (new URLSearchParams(location.search).get("shared") && window.caches){
    (async () => {
      try {
        const cache = await caches.open("sv-share-v1");
        const res = await cache.match("/__shared-image");
        if (res){
          const blob = await res.blob();
          await cache.delete("/__shared-image");
          statusEl.textContent = "shared image received";
          decodeImageFile(blob);
          document.getElementById("scan").scrollIntoView({behavior: "smooth"});
        }
      } catch (e) { /* no shared image — normal load */ }
      history.replaceState(null, "", location.pathname);
    })();
  }
  function escapeHtml(s){ return s.replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
}
document.addEventListener("DOMContentLoaded", boot);
})();

/* encoder.js — SV Code transmitter: envelope signing + grid rendering + broadcast.
   Envelopes are signed with the PUBLISHED TEST AUTHORITY key
   (poc/vectors/vectors.json) so scanners can show a real VALID result.
   This key is public test material — never used for production authority. */
"use strict";
const SVEnc = (() => {
const S = SVC;

const GOLDEN_PRIV_HEX = "1fbf0a5d03e1b7db0ef88a9d107d143e8bc2710e4e9ae656956e0f948037f1ba"; // TEST ONLY
const GOLDEN_PUB_HEX  = "02ac1b5e6915999ebbc89be7405a9fa297b0c549583a9cd3aaab750c2abc5aaeb1";
const GOLDEN_PRIV = S.bytesToBig(S.hexToBytes(GOLDEN_PRIV_HEX));
const TARGET_SVC1 = 0x53564331;

function signEnvelope(text){
  const payload = new TextEncoder().encode(text);
  const zero = new Uint8Array(64);
  const env = S.buildEnvelopeFields(TARGET_SVC1, 0x00FF, new Uint8Array(8),
                                    Math.floor(Date.now()/1000), payload, zero);
  const sig = S.ecdsaSign(GOLDEN_PRIV, S.envelopeDigest(env));
  env.set(sig, 21);
  return env;
}

/* renderer — pure spec anchor colors (SV-0001 §2.1) */
const COLORS = { tl:"#00FFFF", tr:"#FF00FF", bl:"#FFFF00", br:"#FF0000" };
function drawFrame(canvas, bits){
  const GRID = 64, INNER = 52, OFFSET = 6;
  const size = canvas.width, cell = size / GRID;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, size, size);
  ctx.fillStyle = COLORS.tl; ctx.fillRect(0, 0, 4*cell, 4*cell);
  ctx.fillStyle = COLORS.tr; ctx.fillRect(60*cell, 0, 4*cell, 4*cell);
  ctx.fillStyle = COLORS.bl; ctx.fillRect(0, 60*cell, 4*cell, 4*cell);
  ctx.fillStyle = COLORS.br; ctx.fillRect(60*cell, 60*cell, 4*cell, 4*cell);
  ctx.fillStyle = "#000000";
  for (let i = 0; i < bits.length; i++){
    if (bits[i]){
      const r = OFFSET + Math.floor(i / INNER), c = OFFSET + (i % INNER);
      ctx.fillRect(c*cell, r*cell, cell + 0.5, cell + 0.5);
    }
  }
}

function makeBroadcaster(canvas, onStats){
  let timer = null, seed = 0, frames = 0;
  return {
    start(content){
      if (timer) clearInterval(timer);
      const stream = S.buildStream(content);
      const K = stream.length / 32;
      const symbols = []; for (let i = 0; i < K; i++) symbols.push(stream.subarray(i*32, i*32+32));
      const cdf = S.solitonCDF(K);
      const mode = (K <= 10) ? "static" : "fountain";
      seed = 0; frames = 0;
      const emit = () => {
        const s = (mode === "static") ? 0 : (seed % 65535) + 1;
        const enc = []; for (let slot = 0; slot < 10; slot++) enc.push(S.encodeSymbol(symbols, cdf, s, slot));
        drawFrame(canvas, S.packFrame(enc, s, 0x01, K));
        frames++; if (mode !== "static") seed++;
        onStats({ env: content.length, stream: stream.length, K,
                  crc: "0x" + S.crc32(content).toString(16).toUpperCase().padStart(8, "0"),
                  mode: mode === "static" ? "STATIC (seed 0, print-ready)" : "FOUNTAIN @ 12 fps",
                  frames });
      };
      emit();
      if (mode !== "static") timer = setInterval(emit, 83);
    }
  };
}

return { signEnvelope, drawFrame, makeBroadcaster, GOLDEN_PUB_HEX, TARGET_SVC1 };
})();

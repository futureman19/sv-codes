/* SV-0003: approved demo mint only. No issuer private key belongs here. */
"use strict";
const SVMint = (() => {
const S = typeof SVC !== "undefined" ? SVC : require("./svc.js");
const ISSUER = "023a6f32a0528c1b02899c3dbd28cd055fa64ca626271578da4b4261076407a11d";
const ORIGIN = "https://sv-mint.fly.dev", TARGET = 0x47454E31;
const text = s => new TextEncoder().encode(s);
function canonical(v){
  if (v === null || typeof v === "string" || typeof v === "boolean") return JSON.stringify(v);
  if (typeof v === "number" && Number.isSafeInteger(v)) return String(v);
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (v && typeof v === "object") return '{' + Object.keys(v).sort().map(k => JSON.stringify(k)+':'+canonical(v[k])).join(',') + '}';
  throw Error("Invalid canonical JSON");
}
function raw(env){ return S.buildEnvelopeFields(env.targetId, env.action, env.params, env.nonce, env.payload, env.signature); }
function signed(env, bytes){ return S.ecdsaVerify(S.parsePubkey(ISSUER), env.signature, S.envelopeDigest(bytes)); }
function token(res){
  try {
    const e = res.env, c = JSON.parse(new TextDecoder("utf-8", {fatal:true}).decode(e.payload));
    if (res.sig !== "valid" || (res.issuer || "").toLowerCase() !== ISSUER || e.action !== 0xC1A1 || e.targetId !== TARGET || !signed(e, raw(e))) return null;
    if (c.col !== "sv-genesis" || c.v !== 3 || c.price !== 0 || c.supply !== 100 || c.endpoint !== ORIGIN || !Number.isSafeInteger(c.exp) || c.exp < 0) return null;
    if (e.payload.length > 227 || S.bytesToHex(e.payload) !== S.bytesToHex(text(canonical(c)))) return null;
    return c;
  } catch (_) { return null; }
}
function verifyReply(r){
  if (!r || typeof r.envelope !== "string" || !/^(?:[0-9a-fA-F]{2}){85,312}$/.test(r.envelope)) throw Error("Malformed signed envelope");
  const bytes = S.hexToBytes(r.envelope), env = S.parseEnvelope(bytes), c = r.cert;
  if (env.action !== 0xA47C || env.targetId !== TARGET || !signed(env, bytes)) throw Error("Invalid mint signature or target");
  if (!c || c.v !== 2 || c.col !== "sv-genesis" || c.item !== "genesis-blade" || c.of !== 100 || !Number.isInteger(r.edition) || r.edition < 1 || r.edition > 100 || c.ed !== r.edition) throw Error("Invalid edition certificate");
  const seed = S.bytesToHex(S.sha256(text("sv-genesis" + r.edition))).slice(0,6);
  if (r.seed !== seed || c.seed !== seed || typeof r.txid !== "string" || !/^[0-9a-f]{64}$/.test(r.txid) || /^0{64}$/.test(r.txid) || c.mint !== r.txid) throw Error("Certificate does not bind transaction, edition and seed");
  if (env.payload.length > 227 || S.bytesToHex(env.payload) !== S.bytesToHex(text(canonical(c)))) throw Error("Certificate bytes differ from signed payload");
  return {bytes, cert:c};
}
function validAddress(a){
  if (typeof a !== "string" || !/^1[1-9A-HJ-NP-Za-km-z]{25,33}$/.test(a)) return false;
  const alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
  let n = 0n; for (const ch of a) n = n*58n + BigInt(alphabet.indexOf(ch));
  let h = n.toString(16); if (h.length % 2) h = '0'+h;
  const b = S.hexToBytes('00'.repeat(a.match(/^1*/)[0].length)+h);
  return b.length === 25 && b[0] === 0 && S.bytesToHex(S.sha256(S.sha256(b.slice(0,21))).slice(0,4)) === S.bytesToHex(b.slice(21));
}
function mount(root, res){
  const c = token(res);
  if (!c) return null; // untrusted pointers are never fetched
  root.replaceChildren(); root.style.display = "block"; root.classList.remove("bad");
  const add = (tag, value, parent = root) => { const el = document.createElement(tag); if (value) el.textContent = value; parent.append(el); return el; };
  add("h3", "SV-GENESIS · Free mint");
  const badge = add("p", "VALID signature · DEMO certificate (publicly known issuer key)"); badge.className = "sig demo";
  add("p", "Not secure production issuance. Signature verification is not confirmed anchoring or proof of ownership.");
  const remaining = add("p", "Checking live availability…"); remaining.setAttribute("aria-live", "polite");
  add("p", "Free · 0 BSV. Paste a mainnet P2PKH address you control, never a seed or private key. Preserve the one-satoshi collectible; ordinary wallets may spend it as funding.");
  const label = add("label", "Your receiving address");
  const address = add("input", "", label); address.type = "text"; address.placeholder = "1…"; address.autocomplete = "off"; address.spellcheck = false; address.maxLength = 34;
  const claim = add("button", "Claim free edition"); claim.className = "btn primary"; claim.disabled = true;
  const refresh = add("button", "Refresh availability"); refresh.className = "btn";
  const message = add("p", ""); message.setAttribute("role", "status");
  const gallery = add("div", ""), personal = add("div", "");
  let disposed = false, busy = false, available = false, completed = false, lockedAddress = null, timer;
  const controllers = new Set();
  // No trusted header-height source is provisioned here. Never substitute HTTP height for verified height.
  const expiryBlocked = c.exp !== 0;
  if (expiryBlocked) message.textContent = "Claim disabled: this token expires at block " + c.exp + ". A verified current chain height is unavailable.";
  function controls(){ claim.disabled = busy || !available || completed || expiryBlocked || !validAddress(address.value.trim()); refresh.disabled = busy; address.disabled = busy || lockedAddress !== null; }
  async function request(path, options = {}){
    const controller = new AbortController(); controllers.add(controller);
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(ORIGIN + "/mint/sv-genesis/" + path, {...options, cache:"no-store", credentials:"omit", redirect:"error", signal:controller.signal});
      const data = await response.json(); return {response, data};
    } finally { clearTimeout(timeout); controllers.delete(controller); }
  }
  function showPersonal(data){
    const verified = verifyReply(data);
    personal.replaceChildren();
    add("h3", "Genesis Blade · edition " + verified.cert.ed, personal);
    const reveal = add("canvas", "", personal); reveal.width = reveal.height = 512; reveal.className = "item-canvas";
    SVReveal.render(reveal, verified.cert.item, verified.cert.seed);
    const toggle = add("button", "Show my code", personal); toggle.className = "btn";
    const code = add("canvas", "", personal); code.width = code.height = 640; code.className = "item-canvas personal-code"; code.hidden = true; code.setAttribute("aria-label", "Signed personal SV Code");
    SVEnc.makeBroadcaster(code, () => {}).start(verified.bytes);
    toggle.addEventListener("click", () => { code.hidden = !code.hidden; toggle.textContent = code.hidden ? "Show my code" : "Hide my code"; });
    const download = add("a", "Save code PNG", personal); download.href = code.toDataURL("image/png"); download.download = "sv-genesis-" + verified.cert.ed + ".png";
    const link = add("a", "View mint transaction", personal); link.href = "https://whatsonchain.com/tx/" + data.txid; link.target = "_blank"; link.rel = "noopener noreferrer";
    add("p", "A copy of this code is not ownership. Ownership follows the one-satoshi output on-chain.", personal);
  }
  function showGallery(records){
    gallery.replaceChildren(); add("h4", "Collection gallery · server-reported mints", gallery);
    for (const r of records.slice(0,100)){
      if (!Number.isInteger(r.edition) || r.edition < 1 || r.edition > 100 || typeof r.txid !== "string" || !/^[0-9a-f]{64}$/.test(r.txid)) continue;
      const entry = add("div", "Edition " + r.edition, gallery);
      const cv = add("canvas", "", entry); cv.width = cv.height = 256; cv.className = "item-canvas";
      const seed = S.bytesToHex(S.sha256(text("sv-genesis" + r.edition))).slice(0,6);
      SVReveal.render(cv, "genesis-blade", seed);
      const recover = add("button", "View / recover code #" + r.edition, entry); recover.className = "btn";
      recover.addEventListener("click", async () => {
        recover.disabled = true;
        try {
          const {response, data} = await request("edition/" + r.edition);
          if (disposed) return;
          if (!response.ok || data.edition !== r.edition || data.txid !== r.txid) throw Error("Receipt unavailable");
          showPersonal(data);
          message.textContent = "Published demo certificate recovered and signature verified. Ownership not verified.";
        } catch (_) { if (!disposed) message.textContent = "Could not verify the published receipt. Refresh and retry."; }
        finally { recover.disabled = false; }
      });
      const link = add("a", "View mint / trace ownership (output 0)", entry); link.href = "https://whatsonchain.com/tx/" + r.txid; link.target = "_blank"; link.rel = "noopener noreferrer";
    }
  }
  async function status(){
    if (disposed || busy) return;
    try {
      const {response, data:d} = await request("status");
      if (disposed) return;
      if (!response.ok || d.col !== c.col || d.supply !== 100 || !Number.isInteger(d.remaining) || d.remaining < 0 || d.remaining > 100) throw Error("Unavailable");
      available = d.remaining > 0;
      remaining.textContent = available ? d.remaining + " / 100 remaining · Free" : (d.pending > 0 ? "All editions reserved · mint recovery pending" : "MINT COMPLETE");
      showGallery(Array.isArray(d.minted) ? d.minted : Array.isArray(d.claims) ? d.claims : []);
    } catch (_) { if (!disposed) { available = false; remaining.textContent = "Live availability unavailable / offline. Refresh to retry."; } }
    controls();
  }
  address.addEventListener("input", controls); refresh.addEventListener("click", status);
  claim.addEventListener("click", async () => {
    if (claim.disabled || disposed) return;
    const a = lockedAddress || address.value.trim();
    busy = true; lockedAddress = a; controls(); message.textContent = "Requesting edition… Do not switch addresses while a claim may be pending.";
    try {
      const {response, data} = await request("claim", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({address:a})});
      if (disposed) return;
      if (response.status === 202 || data.error === "pending" || data.error === "recovery_pending") { message.textContent = "Mint pending recovery. Retry with this same address; no new edition will be requested."; }
      else if (response.ok) {
        showPersonal(data); completed = true;
        message.textContent = "Demo certificate verified. Broadcast reported by server; confirmation and ownership not verified.";
      } else if (response.status === 409 && data.error === "sold_out") { available = false; remaining.textContent = "MINT COMPLETE"; message.textContent = "No editions remain. Browse the collection below."; }
      else if (response.status === 409) message.textContent = "Address already claimed or reserved. Recover a published code from the gallery below; retry this address only if still pending.";
      else if (response.status === 429) message.textContent = "Rate limited. Wait before retrying with the same address.";
      else if (response.status === 502 || response.status === 503) message.textContent = "Mint service or funding temporarily unavailable. Retry with the same address; a broadcast may be pending.";
      else { message.textContent = "Claim rejected. Check the receiving address and refresh before retrying."; if (response.status === 400 || response.status === 422) lockedAddress = null; }
    } catch (_) { if (!disposed) message.textContent = "No verified collectible received. Network failure or invalid response; keep this address and retry safely. A mint may already be pending."; }
    finally { busy = false; if (!disposed) { controls(); await status(); } }
  });
  status(); timer = setInterval(status, 30000);
  return () => { disposed = true; clearInterval(timer); controllers.forEach(x => x.abort()); };
}
return {ISSUER, ORIGIN, token, canonical, verifyReply, validAddress, mount};
})();
if (typeof module !== "undefined") module.exports = SVMint;

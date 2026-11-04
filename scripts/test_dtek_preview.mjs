import { chromium } from "playwright";

const browser=await chromium.launch({headless:true});
try{
 const page=await browser.newPage({viewport:{width:1365,height:850},acceptDownloads:true});
 const errors=[];
 page.on("pageerror",e=>errors.push(e.message));
 await page.goto("http://127.0.0.1:8765/",{waitUntil:"domcontentloaded",timeout:60000});
 await page.locator("#dtekReviewSection").waitFor({state:"attached",timeout:20000});
 if(errors.length)throw Error("Page errors: "+errors.join(" | "));
 // Verify the review widgets and the user's DTEK decision workflow.
 const inputs=["dtekReviewFile","dtekReviewEnable","dtekReviewAddress",
               "dtekReviewTarget","dtekReviewConfirm","dtekReviewReject",
               "dtekReviewReset","dtekReviewExport","dtekReviewImport"];
 for(const id of inputs){
  if(await page.locator("#"+id).count()!==1)throw Error("Missing "+id);
 }
 await page.evaluate(()=>{document.querySelector("#body").hidden=false;for(const group of document.querySelectorAll("details.setting-section"))group.open=true;});
 await page.locator("#visicomPassword").fill("local-synthetic-test-only");
 const envelope=await page.evaluate(async()=>{
  const sample={schemaVersion:2,counts:{candidate_street_type:1},records:[
   {city:"с-ще Бородянка",street:"вул. Центральна",house:"427а",
    status:"candidate_street_type",links:[{source:"visicom",id:"test-v1",
      street:"Центральна",house:"427а"}]}
  ]};
  const b64=bytes=>btoa(String.fromCharCode(...bytes));
  const salt=crypto.getRandomValues(new Uint8Array(16));
  const iv=crypto.getRandomValues(new Uint8Array(12));
  const pass=await crypto.subtle.importKey("raw",new TextEncoder().encode("local-synthetic-test-only"),"PBKDF2",false,["deriveKey"]);
  const key=await crypto.subtle.deriveKey({name:"PBKDF2",salt,iterations:210000,hash:"SHA-256"},pass,{name:"AES-GCM",length:256},false,["encrypt"]);
  const ciphertext=await crypto.subtle.encrypt({name:"AES-GCM",iv},key,new TextEncoder().encode(JSON.stringify(sample)));
  return {version:1,kdf:"PBKDF2-SHA256",iterations:210000,salt:b64(salt),iv:b64(iv),data:b64(new Uint8Array(ciphertext))};
 });
 await page.locator("#dtekReviewFile").setInputFiles({
  name:"synthetic-dtek-review.enc.json",
  mimeType:"application/json",
  buffer:Buffer.from(JSON.stringify(envelope))
 });
 await page.waitForFunction(()=>document.querySelector("#dtekReviewStatus").textContent.includes("Завантажено 1"),null,{timeout:20000});
 await page.locator("#dtekReviewAddress").selectOption("0");
 await page.locator("#dtekReviewTarget").selectOption("0");
 await page.locator("#dtekReviewConfirm").click();
 await page.waitForFunction(()=>document.querySelector("#dtekReviewDecisionStatus").textContent.includes("1 / 1"));
 const downloadPromise=page.waitForEvent("download");
 await page.locator("#dtekReviewExport").click();
 const download=await downloadPromise;
 if(download.suggestedFilename()!=="dtek-borodianka-manual-decisions.json")throw Error("Unexpected review download");
 await page.locator("#dtekReviewReset").click();
 await page.locator("#dtekReviewImport").setInputFiles({
  name:"review-decisions.json",
  mimeType:"application/json",
  buffer:Buffer.from(JSON.stringify({schemaVersion:1,source:"manual-dtek-borodianka-review",
    decisions:[{city:"с-ще Бородянка",street:"вул. Центральна",house:"427а",
      action:"confirm",source:"visicom",id:"test-v1"}]}))
 });
 await page.waitForFunction(()=>document.querySelector("#dtekReviewDecisionStatus").textContent.includes("Відновлено 1"),null,{timeout:10000});
 if(errors.length)throw Error("Page errors: "+errors.join(" | "));
 console.log("PASS: review DOM, encrypted fixture import, contour choice, approval, JSON export, JSON resume");
}finally{
 await browser.close();
}

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
 // The deployed report is fetched by the map automatically; only the
 // shared Visicom password is needed to decrypt it.
 await page.route("**/data/dtek-all-unified-matches.enc.json",route=>route.fulfill({
  status:200,contentType:"application/json",body:JSON.stringify(envelope)
 }));
 await page.reload({waitUntil:"domcontentloaded"});
 await page.evaluate(()=>{document.querySelector("#body").hidden=false;for(const group of document.querySelectorAll("details.setting-section"))group.open=true;});
 await page.locator("#visicomPassword").fill("local-synthetic-test-only");
 await page.locator("#visicomPassword").dispatchEvent("change");
 await page.waitForFunction(()=>document.querySelector("#dtekReviewStatus").textContent.includes("Завантажено 1"),null,{timeout:20000});
 console.log("PASS: same-site encrypted report loaded automatically after password entry");
 if(await page.locator("#showStreetColors").isChecked())throw Error("Demo street color overlay should be disabled by default");
 if(!await page.locator("#dtekPresenceEnable").isChecked())throw Error("DTEK buildings should be highlighted by default");
 await page.evaluate(()=>{
  applyVisicomFeatures({type:"FeatureCollection",metadata:{mergedBuildings:true,visicom:1,osmSupplemental:0,osmSkippedOverlap:0},features:[{
   type:"Feature",geometry:{type:"Polygon",coordinates:[[[29.61,50.63],[29.6102,50.63],[29.6102,50.6302],[29.61,50.6302],[29.61,50.63]]]},
   properties:{source:"visicom",sourceId:"test-v1",visicomId:"test-v1",street:"Центральна",name:"427а",housenumber:"427а"}
  }]});
 });
 await page.waitForFunction(()=>document.querySelector("#dtekPresenceStatus").textContent.includes("Підсвічено 1"),null,{timeout:20000});
 const popupCount=await page.evaluate(()=>{
  let text="";
  dtekPresenceLayer.eachLayer(layer=>layer.eachLayer(polygon=>{text+=polygon.getPopup()?.getContent()?.textContent||"";}));
  return text;
 });
 if(!popupCount.includes("вул. Центральна")||!popupCount.includes("427а")||!popupCount.includes("ДТЕК"))throw Error("DTEK building popup lacks address and source label");
 console.log("PASS: default no street colors; DTEK buildings highlighted with clickable address popup");

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

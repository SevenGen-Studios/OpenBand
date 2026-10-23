const assert=require('node:assert/strict');
const fs=require('node:fs');
const P=require('../assets/provinces.js');
const data=JSON.parse(fs.readFileSync('data.json','utf8')).bands;
assert.equal(data.filter(b=>P.inProvince(b,'AB')).length,48);
assert.equal(data.filter(b=>P.inProvince(b,'SK')).length,69);
assert.equal(data.filter(b=>P.inProvince(b,'AB')&&b.treaty==='Treaty 7').length,7);
assert.equal(data.filter(b=>P.matches(b,'Goodfish')).length,1);
assert.equal(data.filter(b=>P.matches(b,"Smith's Landing")).length,1);
assert.equal(data.filter(b=>P.matches(b,'462')).length,2);
// Common spelling/punctuation variants must resolve against the real directory.
for(const query of ['Beardys & Okemasis', 'Beardy’s & Okemasis’', 'Beardys and Okemasis']){
 const matches=data.filter(b=>P.inProvince(b,'SK')&&P.matches(b,query));
 assert.equal(matches.length,1,query);assert.equal(matches[0].id,369);
}
for(const query of ['OChiese', 'O’Chiese', "O'Chiese", 'O Chiese']){
 const matches=data.filter(b=>P.inProvince(b,'AB')&&P.matches(b,query));
 assert.equal(matches.length,1,query);assert.equal(matches[0].name,"O'Chiese");
}
assert.equal(data.filter(b=>P.inProvince(b,'AB')&&P.matches(b,'Beardys & Okemasis')).length,0);
assert.equal(P.matches({name:'Cowessess First Nation'},'unrelated nation'),false);
for(const [query,name] of [['Tsuut ina',"Tsuut'ina Nation"],['Kapawe no',"Kapawe'no First Nation"],["Duncan s First Nation","Duncan's First Nation"],["Smith s Landing","Tthebatthie Denesųłiné Nation"]]){
 const matches=data.filter(b=>P.matches(b,query));assert.equal(matches.length,1,query);assert.equal(matches[0].name,name);
}
assert.equal(P.matches({name:'O Chiese'},"O'Chiese"),true);

assert.equal(P.fromPath('/saskatchewan/'),'SK');
assert.equal(P.fromPath('/sk'),'SK');
assert.equal(P.fromPath('/alberta/index.html'),'AB');
assert.equal(P.fromPath('/ab/'),'AB');
assert.equal(P.fromPath('/first-nations/keeseekoose-first-nation/'),'');
assert.equal(P.routeFor('SK'),'/saskatchewan/');
assert.equal(P.routeFor('AB'),'/alberta/');
const bands=[{id:1,province:'AB'},{id:2,province:'AB'},{id:3,province:'SK'},{id:4,province:'AB'}];
const capital={bands:{1:{years:{'2024-2025':{parseStatus:'parsed',publishable:true,totalRevenue:100,totalAssets:null,sha256:'same'}}},2:{years:{'2023-2024':{parseStatus:'parsed',totalRevenue:500},'2024-2025':{parseStatus:'manual_review',publishable:false,totalRevenue:900}}},3:{years:{'2024-2025':{parseStatus:'parsed',totalRevenue:600}}},4:{years:{'2024-2025':{parseStatus:'parsed',totalRevenue:100,sha256:'same'}}}}};
const subtotal=P.aggregate(bands,capital,'AB','2024-2025');
assert.equal(subtotal.reporting,1);assert.equal(subtotal.fields.totalRevenue.total,100);
assert.equal(subtotal.fields.totalAssets.total,null);assert.equal(subtotal.fields.totalAssets.reporting,0);
assert.equal(P.aggregate(bands,capital,'AB','2025-2026').fields.totalRevenue.total,null);
console.log('Province routes, aliases, treaties, fiscal years, null values and duplicate-source checks passed.');

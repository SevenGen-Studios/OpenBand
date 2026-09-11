'use strict';
document.querySelectorAll('[data-current-year]').forEach(node=>{node.textContent=String(new Date().getFullYear())});
(async function(){
  const el=id=>document.getElementById(id);
  const center={lon:-108.40885,lat:54.52212};
  const views={home:{lon:center.lon,lat:center.lat,range:1950,heading:335,pitch:-39},extent:{lon:-108.3735,lat:54.4202,range:18500,heading:0,pitch:-70}};
  let viewer,terrainProvider;
  const collections={buildings:[],boundary:[],labels:[]};
  const fly=(view,duration=1.4)=>viewer.camera.flyToBoundingSphere(new Cesium.BoundingSphere(Cesium.Cartesian3.fromDegrees(view.lon,view.lat),1),{offset:new Cesium.HeadingPitchRange(Cesium.Math.toRadians(view.heading),Cesium.Math.toRadians(view.pitch),view.range),duration});
  const setViewButton=active=>document.querySelectorAll('.view-switcher button').forEach(button=>button.classList.toggle('active',button.id===active));
  const positions=coords=>Cesium.Cartesian3.fromDegreesArray(coords.flat());
  const properties=(feature,type)=>({...feature.properties,featureType:type});
  const polygonHierarchy=rings=>new Cesium.PolygonHierarchy(positions(rings[0]),rings.slice(1).map(ring=>new Cesium.PolygonHierarchy(positions(ring))));
  const polygons=feature=>feature.geometry.type==='Polygon'?[feature.geometry.coordinates]:feature.geometry.coordinates;
  const midpoint=coords=>coords[Math.floor(coords.length/2)];

  function addPolygon(feature,rings,type,style){
    return viewer.entities.add({properties:properties(feature,type),polygon:{hierarchy:polygonHierarchy(rings),material:style.material,height:0,heightReference:Cesium.HeightReference.CLAMP_TO_GROUND,extrudedHeight:style.extrudedHeight,extrudedHeightReference:style.extrudedHeight?Cesium.HeightReference.RELATIVE_TO_GROUND:undefined,shadows:style.shadows||Cesium.ShadowMode.DISABLED}});
  }
  function addLabel(text,coords){
    if(!text)return;
    collections.labels.push(viewer.entities.add({position:Cesium.Cartesian3.fromDegrees(coords[0],coords[1],8),label:{text,font:'600 12px system-ui',fillColor:Cesium.Color.WHITE,outlineColor:Cesium.Color.BLACK.withAlpha(.8),outlineWidth:3,style:Cesium.LabelStyle.FILL_AND_OUTLINE,heightReference:Cesium.HeightReference.RELATIVE_TO_GROUND,disableDepthTestDistance:3500,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,9000),pixelOffset:new Cesium.Cartesian2(0,-8)}}));
  }
  function showFeature(entity){
    const props=entity.properties;
    if(!props||!props.featureType)return;
    const value=name=>props[name]&&props[name].getValue?props[name].getValue():props[name];
    const type=value('featureType');
    const title=value('name')||value('SHORT_NAME')||(type==='Building'?'Mapped building':type==='Road'?'Mapped road':'Water feature');
    const buildingUse=value('amenity')||value('office')||value('shop')||value('building');
    const heightSource=value('heightSource');
    el('featureType').textContent=type;
    el('featureTitle').textContent=title;
    el('featureInfo').textContent=type==='Building'?(heightSource==='Illustrative default'?`OSM footprint${buildingUse?`; mapped type: ${buildingUse}`:''}. Height is illustrative.`:`OSM footprint${buildingUse?`; mapped type: ${buildingUse}`:''}. Display height ${value('renderHeight')} m from ${heightSource}.`):type==='Road'?`OpenStreetMap classification: ${value('highway')||'unspecified'}.`:type==='Reserve boundary'?'ISC administrative reserve boundary, land ID 06603.':type==='Named place'?`Named ${value('place')||value('amenity')||value('leisure')||'place'} recorded in OpenStreetMap.`:'Water geometry recorded in OpenStreetMap.';
    el('featureSource').href=value('sourceUrl')||'https://data.sac-isc.gc.ca/geomatics/rest/services/ILRS_PRD/ERIP_E_NRCan/MapServer/26';
    el('selection').hidden=false;
  }

  try{
    if(!window.Cesium)throw new Error('The 3D map engine could not load.');
    const names=['reserve','buildings','roads','water','poi','metadata'];
    const values=await Promise.all(names.map(async name=>{const response=await fetch(`data/${name}.${name==='metadata'?'json':'geojson'}`);if(!response.ok)throw new Error('Map data unavailable.');return response.json();}));
    const data=Object.fromEntries(names.map((name,index)=>[name,values[index]]));
    try{terrainProvider=await Cesium.ArcGISTiledElevationTerrainProvider.fromUrl('https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer');}catch(error){console.warn('Terrain unavailable:',error);}
    viewer=new Cesium.Viewer('map',{animation:false,baseLayer:false,baseLayerPicker:false,fullscreenButton:false,geocoder:false,homeButton:false,infoBox:false,navigationHelpButton:false,sceneModePicker:false,selectionIndicator:false,timeline:false,terrainProvider:terrainProvider||new Cesium.EllipsoidTerrainProvider(),requestRenderMode:true});
    const imageryProvider=await Cesium.ArcGisMapServerImageryProvider.fromUrl('https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer');
    viewer.imageryLayers.addImageryProvider(imageryProvider);
    viewer.scene.globe.enableLighting=true;
    viewer.scene.globe.depthTestAgainstTerrain=true;
    viewer.scene.globe.baseColor=Cesium.Color.fromCssColorString('#1b2b20');
    viewer.scene.fog.enabled=true;
    viewer.scene.highDynamicRange=true;
    viewer.scene.postProcessStages.fxaa.enabled=true;
    const cameraControls=viewer.scene.screenSpaceCameraController;
    cameraControls.enableZoom=true;
    cameraControls.minimumZoomDistance=120;
    cameraControls.maximumZoomDistance=30000;
    cameraControls.zoomFactor=3.5;

    for(const feature of data.water.features){
      if(feature.geometry.type==='LineString')viewer.entities.add({properties:properties(feature,'Water'),polyline:{positions:positions(feature.geometry.coordinates),width:3,material:Cesium.Color.fromCssColorString('#75b9c7').withAlpha(.8),clampToGround:true}});
      else for(const rings of polygons(feature))for(const ring of rings)viewer.entities.add({properties:properties(feature,'Water'),polyline:{positions:positions(ring),width:2,material:Cesium.Color.fromCssColorString('#79d2e0').withAlpha(.65),clampToGround:true}});
      if(feature.properties.name){const coords=feature.geometry.type==='LineString'?feature.geometry.coordinates:polygons(feature)[0][0];addLabel(feature.properties.name,midpoint(coords));}
    }
    const seenRoadLabels=new Set();
    for(const feature of data.roads.features){
      viewer.entities.add({properties:properties(feature,'Road'),polyline:{positions:positions(feature.geometry.coordinates),width:feature.properties.highway==='primary'?4:2,material:Cesium.Color.WHITE.withAlpha(.72),clampToGround:true}});
      if(feature.properties.name&&!seenRoadLabels.has(feature.properties.name)){seenRoadLabels.add(feature.properties.name);addLabel(feature.properties.name,midpoint(feature.geometry.coordinates));}
    }
    for(const feature of data.reserve.features)for(const rings of polygons(feature)){const entity=addPolygon(feature,rings,'Reserve boundary',{material:Cesium.Color.fromCssColorString('#4ca566').withAlpha(.10)});collections.boundary.push(entity);for(const ring of rings)collections.boundary.push(viewer.entities.add({properties:properties(feature,'Reserve boundary'),polyline:{positions:positions(ring),width:3,material:Cesium.Color.fromCssColorString('#7be092'),clampToGround:true}}));}
    for(const feature of data.buildings.features)for(const rings of polygons(feature)){const sourced=feature.properties.heightSource!=='Illustrative default';const entity=addPolygon(feature,rings,'Building',{material:Cesium.Color.fromCssColorString(sourced?'#a6d5b1':'#d7ddd4').withAlpha(.93),extrudedHeight:Number(feature.properties.renderHeight)||4,shadows:Cesium.ShadowMode.ENABLED});collections.buildings.push(entity);if(feature.properties.name)addLabel(feature.properties.name,feature.geometry.coordinates[0][0]);}
    for(const feature of data.poi.features){const coords=feature.geometry.coordinates;addLabel(feature.properties.name,coords);viewer.entities.add({position:Cesium.Cartesian3.fromDegrees(coords[0],coords[1],5),properties:properties(feature,'Named place'),point:{pixelSize:9,color:Cesium.Color.fromCssColorString('#8bd29c'),outlineColor:Cesium.Color.WHITE,outlineWidth:2,heightReference:Cesium.HeightReference.RELATIVE_TO_GROUND,disableDepthTestDistance:4000}});}

    el('loading').hidden=true;
    fly(views.home,0);
    for(const id of ['home','extent'])el(id).onclick=()=>{setViewButton(id);fly(views[id]);};
    el('buildings').onchange=event=>{collections.buildings.forEach(entity=>entity.show=event.target.checked);viewer.scene.requestRender();};
    el('labels').onchange=event=>{collections.labels.forEach(entity=>entity.show=event.target.checked);viewer.scene.requestRender();};
    el('boundary').onchange=event=>{collections.boundary.forEach(entity=>entity.show=event.target.checked);viewer.scene.requestRender();};
    el('close').onclick=()=>el('selection').hidden=true;
    document.addEventListener('keydown',event=>{if(event.key==='Escape')el('selection').hidden=true;});
    const handler=new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction(event=>{const picked=viewer.scene.pick(event.position);if(Cesium.defined(picked)&&picked.id)showFeature(picked.id);},Cesium.ScreenSpaceEventType.LEFT_CLICK);
  }catch(error){console.error(error);el('loading').innerHTML=`<strong>Map unavailable</strong><small>${error.message} Use the community profile link above.</small>`;}
})();

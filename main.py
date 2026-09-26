from fastapi import FastAPI
import ee
# from geopy.geocoders import Nominatim
import requests

app=FastAPI(title="GeoGuardian Dynamic API")

try:
    ee.Initialize(project='sacred-store-468008-c8')
except Exception as e:
    ee.Authenticate()
    ee.Initialize(project='sacred-store-468008-c8')


def get_address(lat,lon):
    try:
        url=f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"  
        headers={'User-Agent':'GeoGuardian Dashboard'}
        response=requests.get(url,headers=headers,timeout=3)
        if response.status_code==200:
            data=response.json()
            if "display_name" in data:
                parts=data["display_name"].split(',')
                return ", ".join(parts[:3]).strip()
        return f"Coordinates: {round(lat,4)}, {round(lon,4)}"
    except Exception as e:
        print(f"Error during getting address: {str(e)}")
        return f"Coordinates: {round(lat,4)}, {round(lon,4)}"


@app.get("/api/analyze")
def analyze_area(city:str,year:int):
    if city=="Multan":
        coords=[71.45,30.2]
    elif city=="Lahore":
        coords=[74.35,31.52]
    else:
        coords=[73.13,31.45] 

    aoi=ee.Geometry.Point(coords).buffer(15000)
    total_aoi=round(aoi.area().getInfo() / 1e6,2)
    dw_base=ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(aoi).filterDate("2016-01-01","2016-12-31").select('label').mode().clip(aoi)
    dw_current=ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(aoi).filterDate(f"{year}-01-01",f"{year}-12-31").select('label').mode().clip(aoi)
    agri_base=dw_base.eq(4)
    builtup_current=dw_current.eq(6)
    conversion_mask=agri_base.And(builtup_current).selfMask()
    pixel_area=ee.Image.pixelArea()

    converted_area_calc=conversion_mask.multiply(pixel_area).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=aoi,
        scale=100,
        maxPixels=1e10
    ).getInfo()

    current_builtup_calc=builtup_current.selfMask().multiply(pixel_area).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=aoi,
        scale=100,
        maxPixels=1e10
    ).getInfo()

    agriculture_lost=round(converted_area_calc.get('label', 0) / 1e6, 2) if converted_area_calc and 'label' in converted_area_calc else 0.0
    builtup_sqkm=round(current_builtup_calc.get('label', 0) / 1e6, 2) if current_builtup_calc and 'label' in current_builtup_calc else 0.0
    
    percentage_converted=round((agriculture_lost / total_aoi) * 100,2)
    hotspots=[]
    if agriculture_lost>0.5:
        vectors=conversion_mask.reduceToVectors(
            geometry=aoi,
            crs='EPSG:4326',
            # crs=conversion_mask.projection(),
            scale=800,
            geometryType='polygon',
            eightConnected=False,
            maxPixels=1e10
        )
        def add_area(feature):
            return feature.set('area',feature.geometry().area(maxError=1))

        vectors_with_area=vectors.map(add_area)
        top_clusters=vectors_with_area.sort('area',False).limit(3).getInfo()
        if 'features' in top_clusters:
            for feat in top_clusters['features']:
                geom=feat['geometry']['coordinates'][0]
                lon,lat=geom[0][0],geom[0][1]
                real_address=get_address(lat,lon)
                cluster_area=round(feat['properties']['area']/1e6,2)
                hotspots.append({
                    "Area Name/ Location":real_address,
                    "Converted Area (sq km)":f"{cluster_area:.2f}",
                    "Total Impact (%)":f"{round((cluster_area / total_aoi)*100, 2):.2f}"
                })
    
    if percentage_converted>4.0:
        severity="CRITICAL"
        action="Immediate policy intervention is required to restrict unauthorized housing societies."
    elif percentage_converted>2.0:
        severity="MODERATE"
        action="Zoning regulations should be strictly enforced to control further sprawl." 
    else:
        severity="STABLE"
        action="Urban Expansion is currently within sustainable limits."

    ai_summary=f"**{severity} ALERT:** In {year}, {city}'s built-up area is calculated at {builtup_sqkm} sq km using real satellite pixels. Exactly {agriculture_lost} sq km of agricultural land was confirmed as converted to built-up infrastructure since 2016.\n\n**Recommendation:** {action}"

    return {
        "city":city,
        "year":year,
        "total_aoi":total_aoi,
        "agriculture_lost":agriculture_lost,
        "percentage_converted":percentage_converted,
        "builtup_area":builtup_sqkm,
        "ai_summary":ai_summary,
        "hotspots":hotspots
    }

@app.get("/api/geojson")
def get_geojson(city:str):
    if city=="Multan":
        geom=ee.Geometry.Rectangle([71.35,30.10,71.60,30.30])
    elif city=="Lahore":
        geom=ee.Geometry.Rectangle([74.20,31.40,74.50,31.70])
    else:
        geom=ee.Geometry.Rectangle([72.95,31.35,73.20,31.55])

    feature=ee.Feature(geom,{"name":f"{city} AOI Boundary","project":"GeoGuardian Internship Task"})   
    return feature.getInfo()
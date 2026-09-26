import streamlit as st
import requests
import folium
import streamlit.components.v1 as components
import ee
import csv
import io
import json


st.set_page_config(layout="wide",page_title="GeoGuardian Dashboard")
st.title("GeoGuardian: Urban Expansion Monitor")
st.markdown("**Build By Muhammad Khurram - AI/ML Intern**")
st.markdown("Monitoring agricultural land loss and urban builtup expansion using Sentinel-2 and Rnadom Forest")

st.sidebar.header("Analysis Filters")
selected_city=st.sidebar.selectbox("Select District",["Multan","Lahore","Faisalabaad"])
selected_year=st.sidebar.slider("Selected Year",min_value=2016,max_value=2026,value=2026,step=2)
st.sidebar.divider()


API_URL=f"http://127.0.0.1:8000/api/analyze?city={selected_city}&year={selected_year}"
GEO_API_URL=f"http://127.0.0.1:8000/api/geojson?city={selected_city}"

try:
    response=requests.get(API_URL)
    data=response.json()
    geo_response=requests.get(GEO_API_URL)
except requests.exceptions.ConnectionError:
    st.error("Backend Error")
    st.stop()


st.subheader(f"Statistics for {data['city']} ({data['year']})")
col1,col2,col3,col4=st.columns(4)
with col1:
    st.info(f"**Total AOI**\n### {data['total_aoi']} sq km")
with col2:
    st.error(f"**Agriculture Lost**\n### {data['agriculture_lost']} sq km")
with col3:
    st.warning(f"**Percentage Converted**\n### {data['percentage_converted']}%")
with col4:
    st.success(f"**Built-up Area**\n### {data['builtup_area']} sq km")

st.divider()    

st.subheader(f"{selected_city} Micro Lvel Zonel Analysis (Top Expansion Hotspots)")
if "hotspots" in data and len(data["hotspots"])>0:
    st.table(data["hotspots"])
else:
    st.info("No significant isolated cluster found for this timeperiod")

col_btn1,col_btn2=st.columns(2)
output=io.StringIO()
writer=csv.writer(output)
writer.writerow(["---Overall Statistics---"])
writer.writerow(["City","Year","Total Aoi (sq km)","Agriculture Lost (sq km)","Percentage Converted (%)","Built-up Area (sq km)"])
writer.writerow([data['city'],data['year'],data['total_aoi'],data['agriculture_lost'],data['percentage_converted'],data['builtup_area']])
writer.writerow([])
writer.writerow(["---Top Expansion Hotspots---"])
if "hotspots" in data and len(data["hotspots"])>0:
    for h in data["hotspots"]:
        writer.writerow([h["Area Name/ Location"],h["Converted Area (sq km)"],h["Total Impact (%)"]])
else:
    writer.writerow(["No significant isolated clusters found"])

csv_file=output.getvalue().encode('utf-8-sig')
with col_btn1:
    st.download_button(
        label="Download Full data (csv)",
        data=csv_file,
        file_name=f"{selected_city}_Expansion_Stats_{selected_year}.csv",
        mime="text/csv",
        use_container_width=True
    )
try:
    geo_data=geo_response.json()
    if "properties" not in geo_data:
        geo_data["properties"]={}

    geo_data["properties"]["Overall_Stats"]={
        "Total_AOI_sqkm":data['total_aoi'],
        "Agriculture_Lost_sqkm":data['agriculture_lost'],
        "Builtup_Area_sqkm":data['builtup_area'],
        "Percentage_Converted":data['percentage_converted']
    }
    geo_data["properties"]["Hotspots_Data"]=data.get('hotspots',[])
    
    with col_btn2:
        st.download_button(
            label="Download Boundary & Table Data (GeoJSON)",
            data=json.dumps(geo_data,indent=2),
            file_name=f"{selected_city}_Boundary_And_Data_{selected_year}.geojson",
            mime="application/geo+json",
            use_container_width=True
        )
except Exception as e:
    print(f"Error during geojson button: {str(e)}")
    with col_btn2:
        st.error("GeoJSON data currently unavailable")


st.divider()  
try:
    ee.Initialize(project='sacred-store-468008-c8')
except :
    pass

      
st.subheader("AI Generated Insight & Policy Recommendations")
st.info(data['ai_summary'])
st.divider()
st.subheader("Interactive Map")


coords=[30.2,71.45] if selected_city=="Multan" else [31.52,74.35] if selected_city=="Lahore" else [31.45,73.13]
m=folium.Map(location=coords,zoom_start=11)

def add_ee_layer(self,ee_image_object,vis_params,name,show=True):
    map_id_dict=ee.Image(ee_image_object).getMapId(vis_params)
    folium.raster_layers.TileLayer(
        tiles=map_id_dict['tile_fetcher'].url_format,
        attr='Map Data Google Earth Engine',
        name=name,
        overlay=True,
        control=True,
        show=show
    ).add_to(self)

folium.Map.add_ee_layer=add_ee_layer

ee_coords=[coords[1],coords[0]]
aoi_geom=ee.Geometry.Point(ee_coords).buffer(15000)
empty=ee.Image().byte()
aoi_outline=empty.paint(featureCollection=ee.Geometry.Point(ee_coords).buffer(10000),color=1,width=3)
m.add_ee_layer(aoi_outline,{'palette':['black']},f'{selected_city} AOI Boundary')


s2_2016=ee.ImageCollection("COPERNICUS/S2").filterBounds(aoi_geom).filterDate('2016-01-01','2016-12-31').filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).median().clip(aoi_geom)
s2_current=ee.ImageCollection("COPERNICUS/S2").filterBounds(aoi_geom).filterDate(f'{selected_year}-01-01',f'{selected_year}-12-31').filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)).median().clip(aoi_geom)

rgb_vis_params={
    'min':0,
    'max':3000,
    'bands':
    ['B4','B3','B2']
    }
m.add_ee_layer(s2_2016,rgb_vis_params,'RGB Map (2016)')
m.add_ee_layer(s2_current,rgb_vis_params,f'RGB Map ({selected_year})')

ndvi_2016=s2_2016.normalizedDifference(['B8','B4']).rename('NDVI')
ndvi_current=s2_current.normalizedDifference(['B8','B4']).rename('NDVI')
ndvi_vis_params={
    'min':0.0,
    'max':0.8,
    'palette':[
        '#d73027','#f46d43','#fdae61','#fee08b','#d9ef8b','#a6d96a','#66bd63','#1a9850'
        ]
}
m.add_ee_layer(ndvi_2016,ndvi_vis_params,'NDVI (Greenary) 2016')
m.add_ee_layer(ndvi_current,ndvi_vis_params,f'NDVI (Greenary) {selected_year}')

ndbi_2016=s2_2016.normalizedDifference(['B11','B8']).rename('NDBI')
ndbi_current=s2_current.normalizedDifference(['B11','B8']).rename('NDBI')
ndbi_vis_params={
    'min':-0.2,
    'max':0.4,
    'palette':[
        '#2c7bb6','#abd9e9','#ffffbf','#fdae61','#d7191c'
        ]
}
m.add_ee_layer(ndbi_2016,ndbi_vis_params,'NDBI (Built-up) 2016')
m.add_ee_layer(ndbi_current,ndbi_vis_params,f'NDBI (Builtup) {selected_year}')

dw_2016=ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(aoi_geom).filterDate("2016-01-01","2016-12-31").select('label').mode().clip(aoi_geom)
dw_current_yr=ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(aoi_geom).filterDate(f"{selected_year}-01-01",f"{selected_year}-12-31").select('label').mode().clip(aoi_geom)
agri_2016=dw_2016.eq(4)
builtup_now=dw_current_yr.eq(6)
change_mask=agri_2016.And(builtup_now).selfMask()
change_mask=agri_2016.And(builtup_now).selfMask()

landcover=ee.ImageCollection("ESA/WorldCover/v100").first().clip(aoi_geom)
builtup=landcover.eq(50).selfMask()
m.add_ee_layer(builtup,{'palette':['red']},'Urban/Built-up Area')
agriculture=landcover.eq(40).selfMask()
m.add_ee_layer(agriculture,{'palette':['lightgreen']},'Agriculture Land')

folium.LayerControl(collapsed=False).add_to(m)

components.html(m._repr_html_(),height=600)


       

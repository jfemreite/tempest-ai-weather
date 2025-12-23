import streamlit as st
import requests
import google.generativeai as genai
import os
import datetime
import time
import pandas as pd
import altair as alt
from dotenv import load_dotenv
from zoneinfo import ZoneInfo 

# 1. Load Keys
load_dotenv()
TEMPEST_TOKEN = os.getenv("TEMPEST_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 2. Configure Gemini
if not GEMINI_API_KEY:
    st.error("Gemini Key missing.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

try:
    model = genai.GenerativeModel('gemini-2.5-flash')
except:
    model = genai.GenerativeModel('gemini-1.5-flash')

# 3. Helper Functions

def deg_to_compass(num):
    if num is None: return "Unknown"
    val = int((num / 22.5) + .5)
    arr = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return arr[(val % 16)]

def get_station_info():
    url = f"https://swd.weatherflow.com/swd/rest/stations?token={TEMPEST_TOKEN}"
    try:
        resp = requests.get(url).json()
        station = resp['stations'][0]
        return {
            "id": station['station_id'],
            "lat": station['latitude'],
            "lon": station['longitude']
        }
    except Exception as e:
        st.error(f"Error finding station: {e}")
        st.stop()

def get_tempest_forecast(station_id):
    url = f"https://swd.weatherflow.com/swd/rest/better_forecast?station_id={station_id}&units_temp=f&units_wind=mph&units_pressure=inhg&units_precip=in&units_distance=mi&token={TEMPEST_TOKEN}"
    return requests.get(url).json()

def get_nws_alerts(lat, lon):
    headers = {'User-Agent': '(my-weather-app, contact@example.com)'}
    url = f"https://api.weather.gov/alerts/active?point={lat},{lon}"
    try:
        resp = requests.get(url, headers=headers).json()
        if 'features' in resp and len(resp['features']) > 0:
            return [f['properties'] for f in resp['features']]
        return []
    except:
        return []

# --- APP SETUP ---
st.set_page_config(page_title="Ramsey Ct. Weather", page_icon="☁️")
st.title("☁️ Ramsey Ct. Weather")

if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({"role": "assistant", "content": "I'm monitoring Ramsey Ct. conditions. Ask me anything!"})

# --- DATA FETCHING ---
try:
    if "weather_data" not in st.session_state:
        with st.spinner('Updating Ramsey Ct. data...'):
            station_info = get_station_info()
            st.session_state.station_info = station_info
            st.session_state.weather_data = get_tempest_forecast(station_info['id'])
            st.session_state.alerts = get_nws_alerts(station_info['lat'], station_info['lon'])
            
            if "weekly_outlook" in st.session_state:
                del st.session_state.weekly_outlook
    
    data = st.session_state.weather_data
    alerts = st.session_state.alerts

    # --- PARSING DATA ---
    current = data.get('current_conditions', {})
    
    # Dashboard Variables
    curr_cond_text = current.get('conditions', 'Unknown')
    curr_temp = current.get('air_temperature', 0.0)
    curr_hum = current.get('relative_humidity', 0.0)
    curr_wind = current.get('wind_avg', 0.0)
    curr_dir_deg = current.get('wind_direction', 0)
    curr_rain = current.get('precip_accum_local_day', 0.0)
    curr_pres = current.get('sea_level_pressure', 0.0)
    curr_trend_raw = current.get('pressure_trend', '') 
    curr_dir_cardinal = deg_to_compass(curr_dir_deg)

    # 5-Day Forecast Text
    daily_forecast_text = ""
    try:
        daily_data = data['forecast']['daily'][:7] 
        for day in daily_data:
            day_ts = day['day_start_local']
            # TIMEZONE FIX 1: Convert Forecast Text to Pacific
            day_dt = datetime.datetime.fromtimestamp(day_ts, ZoneInfo("US/Pacific"))
            day_name = day_dt.strftime('%A')
            
            high = day.get('air_temp_high', 'N/A')
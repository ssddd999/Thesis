import streamlit as st
import pandas as pd
import paho.mqtt.client as mqtt
import time
import random
from datetime import datetime
import altair as alt

# ==========================================
# 1. PAGE CONFIGURATION & MEMORY INIT
# ==========================================
st.set_page_config(page_title="IoT Scale HMI", page_icon="⚖️", layout="wide")

if 'history' not in st.session_state:
    st.session_state.history = pd.DataFrame(columns=['Time', 'Weight (g)'])

if 'network_history' not in st.session_state:
    st.session_state.network_history = pd.DataFrame(columns=['Time', 'RSSI (dBm)', 'Packet Loss (%)', 'Total Transmissions', 'Latency (ms)'])

# ==========================================
# 2. MQTT CACHED CONNECTION
# ==========================================
@st.cache_resource
def start_mqtt():
    client_id = f"staney_dash_{random.randint(1000, 9999)}"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    
    client.latest_payload = 0.0 
    client.sample_count = 0  
    client.failed_pubs = 0
    client.total_pubs = 0
    client.rssi = 0
    client.last_msg_time = 0.0
    client.network_latency = 0 

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe("staney/scale/weight")
            client.subscribe("staney/scale/network")
            print("✅ Dashboard Subscribed")

    def on_message(client, userdata, message):
        topic = message.topic
        raw_str = message.payload.decode("utf-8")
        
        client.last_msg_time = time.time() 
        
        if topic == "staney/scale/weight":
            try:
                # --- NTP Auto-Latency Parsing ---
                parts = raw_str.split("|")
                
                # Part 1: The actual weight
                client.latest_payload = float(parts[0])
                client.sample_count += 1  
                
                # Part 2: The NTP Epoch Timestamp from ESP32
                if len(parts) > 1:
                    sent_time_ms = int(parts[1])
                    current_time_ms = int(time.time() * 1000)
                    
                    # Calculate exactly how long it took to travel
                    auto_latency = current_time_ms - sent_time_ms
                    
                    if auto_latency >= 0:
                        client.network_latency = auto_latency
            except:
                pass
                
        elif topic == "staney/scale/network":
            try:
                parts = raw_str.split("|")
                if len(parts) == 3:
                    client.failed_pubs = int(parts[0])
                    client.total_pubs = int(parts[1])
                    client.rssi = int(parts[2])
            except:
                pass

    client.on_connect = on_connect
    client.on_message = on_message
    
    client.tls_set()
    client.username_pw_set("Thesis", "Staneychiang12")
    client.connect("3dd5708713a94191ab75d9b92812e7bf.s1.eu.hivemq.cloud", 8883)
    client.loop_start()
    
    return client

mqtt_c = start_mqtt()

# ==========================================
# 3. HELPER: DATA LOGGING
# ==========================================
def log_data():
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_since_last_msg = time.time() - mqtt_c.last_msg_time
    esp_is_online = time_since_last_msg < 5.0
    packet_loss = (mqtt_c.failed_pubs / mqtt_c.total_pubs * 100) if mqtt_c.total_pubs > 0 else 0.0

    if esp_is_online:
        new_weight = pd.DataFrame({'Time': [current_time], 'Weight (g)': [mqtt_c.latest_payload]})
        st.session_state.history = pd.concat([st.session_state.history, new_weight], ignore_index=True).tail(600) 
        
        new_net = pd.DataFrame({
            'Time': [current_time],
            'RSSI (dBm)': [mqtt_c.rssi],
            'Packet Loss (%)': [round(packet_loss, 1)],
            'Total Transmissions': [mqtt_c.total_pubs],
            'Latency (ms)': [mqtt_c.network_latency] 
        })
        st.session_state.network_history = pd.concat([st.session_state.network_history, new_net], ignore_index=True).tail(600)
        
    return esp_is_online, packet_loss


# ==========================================
# 4. ISOLATED PAGE FRAGMENTS
# ==========================================

@st.fragment(run_every=1)
def show_live_feed():
    esp_is_online, packet_loss = log_data()
    
    st.header("📊 Live Weight")
    
    lcd_style = """
    <style>
    .lcd-text {
        font-family: 'Courier New', Courier, monospace;
        font-size: 110px !important;
        font-weight: bold;
        color: #2c3e50;
        margin: 0;
        line-height: 1;
        justify-content: center;
        text-align: center;
    }
    .lcd-unit {
        font-size: 45px;
        color: #7f8c8d;
    }
    </style>
    """
    st.markdown(lcd_style, unsafe_allow_html=True)

    display_weight = f"{mqtt_c.latest_payload:.1f}" if esp_is_online else "--.-"
    
    st.markdown(f"""
    <div class="lcd-container">
        <p class="lcd-text">{display_weight} <span class="lcd-unit">g</span></p>
    </div>
    """, unsafe_allow_html=True)

    if st.button("⚖️ Zero / Tare Scale", use_container_width=True):
        mqtt_c.publish("staney/scale/command", "TARE") 
        st.toast("Tare command sent to scale!")

    st.divider()
    
    st.subheader("📡 Network Health Status")
    cn1, cn2, cn3, cn4 = st.columns(4)
    
    conn_status = "🟢 Online" if esp_is_online else "🔴 Offline"
    
    cn1.metric("Status", conn_status)
    cn2.metric("RSSI Signal", f"{mqtt_c.rssi} dBm" if esp_is_online else "-- dBm")
    cn3.metric("Packet Loss", f"{packet_loss:.1f}%" if esp_is_online else "-- %")
    cn4.metric("Total Transmissions", f"{mqtt_c.total_pubs}" if esp_is_online else "--")


@st.fragment(run_every=2)
def show_data_analytics():
    esp_is_online, packet_loss = log_data()
    
    st.header("📈 System Analytics & Logs")
    
    st.subheader("📡 Real-Time Telemetry & Forecasting")
    
    # --- CHANGED: Created 3 columns to fit the AI Predictor ---
    colA, colB, colC = st.columns(3)
    
    with colA:
        st.metric("Package Latency (NTP Auto-Tracked)", f"{mqtt_c.network_latency} ms" if mqtt_c.network_latency > 0 else "-- ms")
    
    with colB:
        st.metric("Total Data Points Collected", f"{mqtt_c.sample_count}")

    # ==========================================
    # 🤖 AI PREDICTIVE FORECASTING ALGORITHM
    # ==========================================
    with colC:
        if len(st.session_state.history) >= 5:
            recent_data = st.session_state.history.tail(5)
            start_weight = recent_data['Weight (g)'].iloc[0]
            current_weight = recent_data['Weight (g)'].iloc[-1]
            weight_lost = start_weight - current_weight
            
            if weight_lost > 2.0:
                rate_per_sec = weight_lost / 5.0 
                if rate_per_sec > 0:
                    seconds_remaining = current_weight / rate_per_sec
                    mins, secs = divmod(int(max(0, seconds_remaining)), 60)
                    
                    st.metric("🤖 Time to Empty", f"{mins}m {secs}s", f"-{rate_per_sec:.1f} g/sec", delta_color="inverse")
                    
                    if mins < 1:
                        st.warning("⚠️ Critical: Low Volume!")
            elif weight_lost < -2.0:
                st.metric("🤖 Time to Empty", "Refilling...", "+ Filling")
            else:
                st.metric("🤖 Time to Empty", "Stable", "0.0 g/sec")
        else:
            st.metric("🤖 Time to Empty", "Gathering data...")

    st.divider()

    st.subheader("Weight Fluctuation Graph")
    if not st.session_state.history.empty:
        df_chart = st.session_state.history.copy()
        df_chart['Time'] = pd.to_datetime(df_chart['Time'])
        
        chart = alt.Chart(df_chart).mark_line(
            color='#1f77b4', 
            strokeWidth=3,
            point=alt.OverlayMarkDef(color='#1f77b4', size=50) 
        ).encode(
            x=alt.X('Time:T', axis=alt.Axis(format='%H:%M:%S', title='Time')),
            y=alt.Y('Weight (g):Q', axis=alt.Axis(title='Weight (g)'))
        ).properties(height=350)
        
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Waiting for data from the ESP32 to generate graph...")

    st.divider()

    with st.expander("⚖️ Historical Weight Data Analysis", expanded=False):
        if not st.session_state.history.empty:
            st.dataframe(st.session_state.history.sort_values(by='Time', ascending=False), use_container_width=True)
            csv_weight = st.session_state.history.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Weight Dataset (CSV)", data=csv_weight, file_name="scale_weight_data.csv", mime="text/csv")
        else:
            st.info("Waiting for weight data from ESP32...")

    with st.expander("📡 Network Health Analysis", expanded=False):
        if not st.session_state.network_history.empty:
            st.dataframe(st.session_state.network_history.sort_values(by='Time', ascending=False), use_container_width=True)
            csv_net = st.session_state.network_history.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Network Dataset (CSV)", data=csv_net, file_name="scale_network_health.csv", mime="text/csv")
        else:
            st.info("Waiting for network telemetry from ESP32...")


def show_system_control():
    st.header("⚙️ Intelligent Calibration & Control")
    st.write("Use this panel to manage the physical scale remotely.")
    
    st.subheader("1. Remote Tare")
    if st.button("🔄 Trigger Remote Tare"):
        mqtt_c.publish("staney/scale/command", "TARE")
        st.success("Tare command published to MQTT broker! The scale will zero out momentarily.")

    st.divider()

    st.subheader("2. Remote Wi-Fi Configuration")
    st.warning("⚠️ Warning: Sending new credentials will cause the scale to immediately reboot.")
    
    with st.form("wifi_config_form"):
        new_ssid = st.text_input("New Wi-Fi Network Name (SSID)", placeholder="e.g., MyHomeNetwork_5G")
        new_password = st.text_input("New Wi-Fi Password", type="password", placeholder="Enter password...")
        
        submit_wifi = st.form_submit_button("📡 Send Credentials to Scale")
        
        if submit_wifi:
            if new_ssid and new_password:
                payload = f"{new_ssid}|{new_password}"
                mqtt_c.publish("staney/scale/wifi", payload)
                st.success(f"Credentials sent! The scale is now rebooting to connect to **{new_ssid}**.")
            else:
                st.error("Please enter both the Network Name and the Password before submitting.")

# ==========================================
# 5. SIDEBAR ROUTING LOGIC
# ==========================================
st.sidebar.title("Scale Menu")
menu = st.sidebar.radio("Navigate", ["📊 Live Feed", "📈 Data Analytics", "⚙️ System Control"])

if menu == "📊 Live Feed":
    show_live_feed()
elif menu == "📈 Data Analytics":
    show_data_analytics()
elif menu == "⚙️ System Control":
    show_system_control()

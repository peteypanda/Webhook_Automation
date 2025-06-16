import time
import logging
import traceback
import requests
from datetime import datetime, timedelta
from requests_kerberos import HTTPKerberosAuth, OPTIONAL
from urllib3 import disable_warnings
import os
import subprocess

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def send_webhook_alert(title, content, footer, appointment_details=None):
    webhook_url = "https://hooks.slack.com/triggers/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"
    details_text = ""
    if appointment_details:
        details_text = "\n".join([f"{k}: {v}" for k, v in appointment_details.items()])
    full_content = content
    if details_text:
        full_content += "\n\nAppointment Details:\n" + details_text
    payload = {
        "title": title,
        "content": full_content,
        "footer": footer,
        "appointment_details": ""
    }
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(webhook_url, json=payload, headers=headers)
        response.raise_for_status()
        logging.info(f"Webhook alert sent: {title}")
    except Exception as e:
        logging.error(f"Failed to send webhook alert: {e}")

def format_time_delta(td):
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

class FCLM:
    def __init__(self, fc: str):
        disable_warnings()
        self.fc = fc.upper()
        self.authenticate()

    def authenticate(self):
        self.cookie = self.mw_cookie()
        self.session = requests.Session()
        self.session.cookies.update(self.cookie)
        self.session.auth = HTTPKerberosAuth(mutual_authentication=OPTIONAL)
        self.session.verify = False
        try:
            response = self.session.get("https://fclm-portal.amazon.com/reports/functionRollup")
            if response.status_code != 200:
                self.reset_mw_cookie()
                self.session.cookies.update(self.cookie)
                response = self.session.get("https://fclm-portal.amazon.com/reports/functionRollup")
            logging.info("Authenticated to FCLM portal")
        except Exception as e:
            logging.error(f"Failed to authenticate to FCLM portal: {e}")
            raise

    def reset_mw_cookie(self, flags: list = None):
        self.cookie = self.mw_cookie(flags=flags, delete_cookie=True)
        self.session.cookies.update(self.cookie)

    def mw_cookie(self, flags=None, delete_cookie: bool = False):
        if flags is None:
            flags = ["--fido2", "--aea"]
        path = os.path.join(os.path.expanduser("~"), ".midway")
        cookie = os.path.join(path, "cookie")
        if delete_cookie and os.path.exists(cookie):
            os.remove(cookie)
        if not os.path.exists(cookie):
            logging.info("Running mwinit for authentication...")
            subprocess.run(["mwinit"] + flags, check=True)
        with open(cookie, "rt") as c:
            cookie_file = c.readlines()
        cookies = {}
        now = time.time()
        for line in range(4, len(cookie_file)):
            if int(cookie_file[line].split("\t")[4]) < now:
                logging.info("Cookie expired, refreshing...")
                subprocess.run(["mwinit"] + flags, check=True)
                return self.mw_cookie(flags=flags)
            cookies[cookie_file[line].split("\t")[5]] = str.replace(
                cookie_file[line].split("\t")[6], "\n", ""
            )
        return cookies

    def get_appointment_data(self, warehouse_id: str, start_date: str, end_date: str):
        url = "https://fc-inbound-dock-execution-service-na-usg1-iad.iad.proxy.amazon.com/appointment/bySearchParams"
        params = {
            "warehouseId": warehouse_id,
            "clientId": "dockmaster",
            "searchResultLevel": "FULL",
            "searchCriteriaName": "DROPOFF_DATE",
            "localStartDate": start_date,
            "localEndDate": end_date,
            "isStartInRange": "true"
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Origin": "https://fc-inbound-dock-hub-na.aka.amazon.com",
            "DNT": "1",
            "Connection": "keep-alive",
            "Referer": "https://fc-inbound-dock-hub-na.aka.amazon.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "TE": "trailers"
        }
        try:
            response = self.session.get(url, params=params, headers=headers)
            response.raise_for_status()
            logging.info(f"Successfully fetched appointment data for {warehouse_id}")
            return response.json()
        except Exception as e:
            logging.error(f"Failed to fetch appointment data for {warehouse_id}: {e}")
            return None

def get_appointment_details(appointment):
    appt_id = appointment['inboundShipmentAppointmentId']
    status = appointment['status']
    carrier = appointment.get('carrierName', 'N/A')
    door = appointment.get('doorNumber', 'N/A')
    comments = "; ".join(appointment.get('comments', [])) if appointment.get('comments') else 'No comments'
    carton_count = appointment.get('cartonCount', 'N/A')
    unit_count = appointment.get('unitCount', 'N/A')
    return {
        "ID": appt_id,
        "Status": status,
        "Carrier Name": carrier,
        "Door Number": door,
        "Comments": comments,
        "Carton Count": carton_count,
        "Unit Count": unit_count
    }

def main():
    # HARDCODED - No user input needed
    fc = "PSC2"
    logging.info(f"Starting automated monitoring for FC {fc}")
    
    # Send startup notification only once per session
    startup_sent = False
    
    if not startup_sent:
        try:
            send_webhook_alert(
                title=f"🚀 Collect Arrivals Monitor Started",
                content=f"Automated monitoring started for FC {fc}\nMonitoring ARRIVAL_SCHEDULED → ARRIVED transitions",
                footer=f"Auto-started by token monitor"
            )
            startup_sent = True
        except Exception as e:
            logging.error(f"Failed to send startup notification: {e}")
    
    fclm = FCLM(fc)
    refresh_interval = 60  # in seconds
    previous_status = {}
    lucy_trackers = {}  # Track compliance state per appointment
    
    # Track notifications sent today to prevent duplicates on restart
    notifications_sent_today = set()
    last_notification_date = None
    
    logging.info(f"Monitoring for ARRIVAL_SCHEDULED -> ARRIVED transitions at FC {fc}...")
    
    while True:
        try:
            now = datetime.now()
            current_date = now.date()
            
            # Reset notification tracker on new day
            if last_notification_date != current_date:
                notifications_sent_today.clear()
                last_notification_date = current_date
                logging.info(f"New day detected: {current_date}. Clearing notification tracker.")
            
            today = datetime.now()
            start_date = today.strftime("%Y-%m-%dT00:00:00")
            end_date = today.strftime("%Y-%m-%dT23:59:59")
            appointment_data = fclm.get_appointment_data(fc, start_date, end_date)
            
            if appointment_data and 'AppointmentList' in appointment_data:
                appointments = appointment_data['AppointmentList']
                
                # Helper functions
                def is_live_load(appt):
                    attrs = appt.get('attributes', {})
                    return attrs.get('CARRIER_LOAD_TYPE', {}).get('value') == 'LIVE'
                
                def is_palletized(appt):
                    attrs = appt.get('attributes', {})
                    return attrs.get('IS_PALLETIZED', {}).get('value') == 'Yes'
                
                # Process appointments
                for appt in appointments:
                    appt_id = str(appt['inboundShipmentAppointmentId'])
                    status = appt['status']
                    prev = previous_status.get(appt_id, None)
                    attrs = appt.get('attributes', {})
                    is_live = attrs.get('CARRIER_LOAD_TYPE', {}).get('value') == 'LIVE'
                    is_palletized_val = attrs.get('IS_PALLETIZED', {}).get('value') == 'Yes'
                    pallet_count = appt.get('palletCount', None)
                    dock_door = appt.get('doorNumber', 'N/A')
                    
                    if not is_live:
                        previous_status[appt_id] = status
                        continue
                    
                    load_type = 'Palletized' if is_palletized_val and (pallet_count and pallet_count > 0) else 'Floor Load'
                    threshold = timedelta(hours=3, minutes=30) if load_type == 'Palletized' else timedelta(hours=7)
                    
                    arrival_time = None
                    if appt.get('arrivalDate') and 'utcMillis' in appt['arrivalDate']:
                        arrival_time = datetime.fromtimestamp(appt['arrivalDate']['utcMillis'] / 1000)
                    elif 'arrivalDates' in appt and appt['arrivalDates'].get('localStartDate') and 'utcMillis' in appt['arrivalDates']['localStartDate']:
                        arrival_time = datetime.fromtimestamp(appt['arrivalDates']['localStartDate']['utcMillis'] / 1000)
                    
                    # Lucy tracker management
                    if appt_id not in lucy_trackers and arrival_time:
                        lucy_trackers[appt_id] = {
                            'status': status,
                            'start_time': arrival_time,
                            'load_type': load_type,
                            'threshold': threshold,
                            'notifications': {
                                'initial': False,
                                'halfway': False,
                                '30min': False,
                                'missed': False,
                                'checked_in': False,
                                'closed': False,
                                'compliance': False
                            }
                        }
                    
                    # Always update status in tracker
                    if appt_id in lucy_trackers:
                        lucy_trackers[appt_id]['status'] = status
                    
                    # Build details
                    details = get_appointment_details(appt)
                    details['Arrival Timestamp'] = arrival_time.strftime('%Y-%m-%d %H:%M:%S') if arrival_time else 'N/A'
                    details['Load Type'] = load_type
                    details['Is Palletized'] = 'Yes' if is_palletized_val and (pallet_count and pallet_count > 0) else 'No'
                    details['Is Live Load'] = 'Yes' if is_live else 'No'
                    details['Status'] = status
                    details['Dock Door'] = dock_door
                    details['LUCY Timer Started'] = arrival_time.strftime('%Y-%m-%d %H:%M:%S') if arrival_time else 'N/A'
                    details['Threshold'] = str(threshold)
                    details['Appointment Details Link'] = f'https://fc-inbound-dock-hub-na.aka.amazon.com/en_US/#/dockmaster/appointment/{fc}/view/{appt_id}/appointmentDetail'
                    
                    notifications = lucy_trackers[appt_id]['notifications'] if appt_id in lucy_trackers else {}
                    
                    # Create unique notification identifiers to prevent duplicates
                    checked_in_id = f"{current_date}_{appt_id}_checked_in"
                    closed_id = f"{current_date}_{appt_id}_closed" 
                    arrived_id = f"{current_date}_{appt_id}_arrived"
                    
                    # Status change notifications (only if not sent today)
                    if (prev == 'ARRIVED' and status == 'CHECKED_IN' and 
                        not notifications.get('checked_in') and 
                        checked_in_id not in notifications_sent_today):
                        
                        now_time = datetime.now()
                        elapsed = (now_time - arrival_time) if arrival_time else timedelta(0)
                        remaining = threshold - elapsed
                        details['Elapsed Time'] = format_time_delta(elapsed)
                        details['Time to Threshold'] = format_time_delta(remaining) if remaining > timedelta(0) else 'EXCEEDED'
                        send_webhook_alert(
                            title="Live Load Checked In",
                            content=(f"Load Type: {load_type}\nAppointment ID: {appt_id}\nYou have {details['Time to Threshold']} to be LUCY compliant.\nDock Door: {dock_door}"),
                            footer=f"FC: {fc}",
                            appointment_details=details
                        )
                        notifications['checked_in'] = True
                        notifications_sent_today.add(checked_in_id)
                    
                    if (prev == 'CHECKED_IN' and status == 'CLOSED' and 
                        not notifications.get('closed') and 
                        closed_id not in notifications_sent_today):
                        
                        now_time = datetime.now()
                        elapsed = (now_time - arrival_time) if arrival_time else timedelta(0)
                        details['Elapsed Time'] = format_time_delta(elapsed)
                        details['Time to Threshold'] = format_time_delta(threshold - elapsed) if threshold - elapsed > timedelta(0) else 'EXCEEDED'
                        if elapsed <= threshold:
                            time_remaining = threshold - elapsed
                            time_remaining_str = format_time_delta(time_remaining)
                            send_webhook_alert(
                                title="Live Load LUCY Compliance Met",
                                content=(f"Load Type: {load_type}\nAppointment ID: {appt_id}\nClosed with {time_remaining_str} remaining to LUCY compliance.\nDock Door: {dock_door}"),
                                footer=f"FC: {fc}",
                                appointment_details=details
                            )
                            notifications['compliance'] = True
                        else:
                            time_exceeded = elapsed - threshold
                            time_exceeded_str = format_time_delta(time_exceeded)
                            send_webhook_alert(
                                title="Live Load LUCY Compliance Missed",
                                content=(f"Load Type: {load_type}\nAppointment ID: {appt_id}\nClosed {time_exceeded_str} after LUCY compliance threshold.\nDock Door: {dock_door}"),
                                footer=f"FC: {fc}",
                                appointment_details=details
                            )
                            notifications['missed'] = True
                        notifications['closed'] = True
                        notifications_sent_today.add(closed_id)
                    
                    if (status == 'ARRIVED' and 
                        not notifications.get('initial') and 
                        arrived_id not in notifications_sent_today):
                        
                        now_time = datetime.now()
                        elapsed = now_time - arrival_time if arrival_time else timedelta(0)
                        remaining = threshold - elapsed
                        details['Elapsed Time'] = format_time_delta(elapsed)
                        details['Time to Threshold'] = format_time_delta(remaining) if remaining > timedelta(0) else 'EXCEEDED'
                        send_webhook_alert(
                            title="LUCY Timer Started - Live Load Arrived",
                            content=(f"Load Type: {load_type}\nAppointment ID: {appt_id}\nDock Door: {dock_door}\nYou have {details['Time to Threshold']} to be LUCY compliant."),
                            footer=f"FC: {fc}",
                            appointment_details=details
                        )
                        notifications['initial'] = True
                        notifications_sent_today.add(arrived_id)
                    
                    previous_status[appt_id] = status
                
                # Check ongoing timers (with duplicate prevention)
                now_time = datetime.now()
                for appt_id, tracker in list(lucy_trackers.items()):
                    if tracker['status'] != 'ARRIVED':
                        continue
                    start_time = tracker['start_time']
                    threshold = tracker['threshold']
                    elapsed = now_time - start_time
                    remaining = threshold - elapsed
                    halfway = threshold / 2
                    
                    details = {
                        'Appointment ID': appt_id,
                        'Load Type': tracker['load_type'],
                        'Is Palletized': 'Yes' if tracker['load_type'] == 'Palletized' else 'No',
                        'Is Live Load': 'Yes',
                        'Status': tracker['status'],
                        'LUCY Timer Started': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'Elapsed Time': format_time_delta(elapsed),
                        'Time to Threshold': format_time_delta(threshold - elapsed) if threshold - elapsed > timedelta(0) else 'EXCEEDED',
                        'Threshold': str(threshold),
                        'Expected Completion Time': (start_time + threshold).strftime('%Y-%m-%d %H:%M:%S'),
                        'Appointment Details Link': f'https://fc-inbound-dock-hub-na.aka.amazon.com/en_US/#/dockmaster/appointment/{fc}/view/{appt_id}/appointmentDetail'
                    }
                    
                    notifications = tracker['notifications']
                    
                    # Create unique notification identifiers
                    halfway_id = f"{current_date}_{appt_id}_halfway"
                    thirty_min_id = f"{current_date}_{appt_id}_30min"
                    missed_id = f"{current_date}_{appt_id}_missed"
                    
                    # Time-based notifications (only if not sent today)
                    if (not notifications['halfway'] and elapsed >= halfway and 
                        halfway_id not in notifications_sent_today):
                        send_webhook_alert(
                            title="LUCY Compliance Halfway",
                            content=(f"Load Type: {tracker['load_type']}\nAppointment ID: {appt_id}\nHalfway to LUCY compliance threshold."),
                            footer=f"FC: {fc}",
                            appointment_details=details
                        )
                        notifications['halfway'] = True
                        notifications_sent_today.add(halfway_id)
                    
                    if (not notifications['30min'] and threshold - elapsed <= timedelta(minutes=30) and 
                        threshold - elapsed > timedelta(seconds=0) and 
                        thirty_min_id not in notifications_sent_today):
                        send_webhook_alert(
                            title="LUCY Compliance Approaching (30 min)",
                            content=(f"Load Type: {tracker['load_type']}\nAppointment ID: {appt_id}\n30 minutes remaining to LUCY compliance threshold."),
                            footer=f"FC: {fc}",
                            appointment_details=details
                        )
                        notifications['30min'] = True
                        notifications_sent_today.add(thirty_min_id)
                    
                    if (not notifications['missed'] and elapsed > threshold and 
                        missed_id not in notifications_sent_today):
                        hours, remainder = divmod(elapsed.total_seconds(), 3600)
                        minutes = remainder // 60
                        send_webhook_alert(
                            title="Live Load LUCY Compliance Missed",
                            content=(f"Load Type: {tracker['load_type']}\nAppointment ID: {appt_id}\nMissed by: {int(hours)} hours and {int(minutes)} minutes"),
                            footer=f"FC: {fc}",
                            appointment_details=details
                        )
                        notifications['missed'] = True
                        notifications_sent_today.add(missed_id)
            else:
                logging.warning("No appointment data found or unexpected format.")
            
            time.sleep(refresh_interval)
            
        except Exception as e:
            logging.error(f"Error in monitoring loop: {e}")
            logging.error(traceback.format_exc())
            time.sleep(60)

if __name__ == "__main__":
    main()
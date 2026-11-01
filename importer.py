#!/usr/bin/env python3
"""Enterprise SD-WAN Monitoring System - Importer Module"""

import pandas as pd
import logging
import os
from database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def detect_timezone(lat, lon):
    """Detect timezone from coordinates"""
    if pd.isna(lat) or pd.isna(lon):
        return 'Asia/Makassar'
    if lon < 105:
        return 'Asia/Jakarta'
    elif lon < 125:
        return 'Asia/Makassar'
    else:
        return 'Asia/Jayapura'
def detect_timezone(lat, lon):
logging.basicConfig(level=logging.INFO)
def detect_timezone(lat, lon):
    """Detect timezone from coordinates"""
    if pd.isna(lat) or pd.isna(lon):
        return 'Asia/Makassar'  # Default WITA (Bank Kalsel)
    if lon < 105:
        return 'Asia/Jakarta'      # WIB (UTC+7)
    COLUMN_MAPPING = {
        'site': ['Site/Cabang', 'Site', 'Cabang', 'Nama Site', 'Site Name', 'site', 'cabang'],
        'ip_lintas': ['IP Lintas', 'IP Lintasarta', 'IP_LA', 'Lintas IP', 'ip_lintas', 'ip lintas'],
        'ip_icon': ['IP ICON', 'IP ICON+', 'IP_ICON', 'ICON IP', 'ip_icon', 'ip icon'],
        'access_type': ['Access Type', 'Media Akses', 'Access', 'Media', 'access_type', 'access type'],
        'nojar_versa': ['Nojar Versa', 'Nojar_Versa', 'Versa Nojar', 'Nojar CPE', 'nojar_versa', 'nojar versa'],
        'nojar_starlink': ['Nojar Starlink', 'Nojar_Starlink', 'Starlink Nojar', 'nojar_starlink', 'nojar starlink'],
        'lat': ['Lat', 'Latitude', 'LAT', 'Lat.', 'lat', 'latitude'],
        'long': ['Long', 'Longitude', 'LONG', 'Long.', 'long', 'longitude'],
        'pic_name': ['Nama PIC', 'PIC Name', 'PIC', 'Nama', 'pic_name', 'pic name', 'nama pic'],
        'pic_phone': ['No WA PIC', 'No. WA PIC', 'WA PIC', 'Phone PIC', 'pic_phone', 'no wa pic'],
        'pic_provider_phone': ['No WA Provider', 'No. WA Provider', 'WA Provider', 'Provider Phone', 'pic_provider_phone', 'no wa provider'],
        'router_versa_name': ['Nama Router Versa', 'Router Versa Name', 'Nama Router', 'Router Name', 'router_versa_name', 'nama router versa'],
        'router_model': ['Model Router', 'Router Model', 'Model', 'router_model', 'model router'],
        'router_versa_regist': ['No Regist Router Versa', 'No. Regist Router Versa', 'Regist Router Versa', 'Router Regist', 'router_versa_regist', 'no regist router versa'],
        'psu_regist': ['No Regist PSU', 'No. Regist PSU', 'Regist PSU', 'PSU Regist', 'psu_regist', 'no regist psu'],
    }
        'pic_provider_phone': ['No WA Provider', 'No. WA Provider', 'WA Provider', 'Provider Phone', 'pic_provider_phone', 'no wa provider'],
    }
    
    def _normalize_columns(self, df):
        """Normalize column names based on mapping"""
        normalized = {}
        for standard, variants in self.COLUMN_MAPPING.items():
            for col in df.columns:
                if col.strip() in variants:
        try:
            df = pd.read_excel(filepath, dtype=str)
            
            # Normalize column names
            df = self._normalize_columns(df)
            
            # Check required columns (after normalization)
            required = ['site', 'ip_lintas', 'ip_icon', 'access_type']
        string_columns = ['site', 'ip_lintas', 'ip_icon', 'access_type', 
                         'nojar_versa', 'nojar_starlink', 'pic_name', 'pic_phone', 'pic_provider_phone',
                         'router_versa_name', 'router_model', 'router_versa_regist', 'psu_regist']
            missing = [col for col in required if col not in df.columns]
            if missing:
                return {"success": False, "error": f"Missing required columns: {missing}. Found: {list(df.columns)}"}
            
            cleaned_data = self._clean_excel_data(df)
            import_result = self._import_to_database(cleaned_data)
            
            logger.info(f"Import completed: {import_result}")
            return {"success": True, "results": import_result}
            
        except Exception as e:
            logger.error(f"Excel import failed: {e}")
            return {"success": False, "error": str(e)}
                    normalized[col] = standard
                    break
        
        # Rename columns
        if normalized:
            df = df.rename(columns=normalized)
        return df
        return 'Asia/Jayapura'     # WIT (UTC+9)

class BranchImporter:
    elif lon < 125:
        return 'Asia/Makassar'     # WITA (UTC+8)
    else:
        return 'Asia/Jayapura'     # WIT (UTC+9)
logger = logging.getLogger(__name__)

class BranchImporter:
    def __init__(self, db_manager=None):
        if db_manager is None:
            db_manager = DatabaseManager()
        self.db_manager = db_manager
        self.expected_columns = [
            'Site/Cabang', 'IP Lintas', 'IP ICON', 'Access Type', 
            'Nojar Versa', 'Nojar Starlink', 'Lat', 'Long', 
            'Nama PIC', 'No WA PIC', 'No WA Provider'
        ]
    
    def import_branches_from_excel(self, filepath):
        if not os.path.exists(filepath):
            return {"success": False, "error": "File not found"}
        
        try:
            df = pd.read_excel(filepath, dtype=str)
            missing_columns = [col for col in self.expected_columns if col not in df.columns]
            if missing_columns:
                return {"success": False, "error": f"Missing columns: {missing_columns}"}
            
            cleaned_data = self._clean_excel_data(df)
            import_result = self._import_to_database(cleaned_data)
            
            logger.info(f"Import completed: {import_result}")
            return {"success": True, "results": import_result}
            
        except Exception as e:
            logger.error(f"Excel import failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _clean_excel_data(self, df):
        df_clean = df.copy()
        df_clean = df_clean.dropna(subset=['Site/Cabang'])
                    access_type = ?, nojar_cpe_versa = ?, nojar_starlink = ?,
                    latitude = ?, longitude = ?, timezone = ?, 
                    router_versa_name = ?, router_model = ?, router_versa_regist = ?, psu_regist = ?,
                    pic_name = ?, pic_phone = ?, pic_provider_phone = ?, updated_at = CURRENT_TIMESTAMP
                WHERE name = ? AND ip = ? AND provider = ?
            ''', (
                row['site'], row['name'], row['ip'], row['provider'],
                row['access_type'], row['nojar_versa'], row['nojar_starlink'],
                row['lat'], row['long'], row['timezone'],
                row['router_versa_name'], row['router_model'], row['router_versa_regist'], row['psu_regist'],
                row['pic_name'], row['pic_phone'], row['pic_provider_phone'],
                row['name'], row['ip'], row['provider']
            ))
        
        string_columns = ['Site/Cabang', 'IP Lintas', 'IP ICON', 'Access Type', 
                         'Nojar Versa', 'Nojar Starlink', 'Nama PIC', 'No WA PIC', 'No WA Provider']
        
        for col in string_columns:
            if col in df_clean.columns:
                df_clean[col] = df_clean[col].fillna('').astype(str).str.strip()
                    (site, name, ip, provider, access_type, 
                     nojar_cpe_versa, nojar_starlink, latitude, longitude, timezone,
                     router_versa_name, router_model, router_versa_regist, psu_regist,
                     pic_name, pic_phone, pic_provider_phone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row['site'], row['name'], row['ip'], row['provider'],
                    row['access_type'], row['nojar_versa'], row['nojar_starlink'],
                    row['lat'], row['long'], row['timezone'],
                    row['router_versa_name'], row['router_model'], row['router_versa_regist'], row['psu_regist'],
                    row['pic_name'], row['pic_phone'], row['pic_provider_phone']
                ))
        
        if 'Lat' in df_clean.columns:
        df_clean['provider'] = df_clean.apply(self._determine_provider, axis=1)
            df_clean['Lat'] = pd.to_numeric(df_clean['Lat'], errors='coerce')
        
        if 'Long' in df_clean.columns:
            df_clean['Long'] = pd.to_numeric(df_clean['Long'], errors='coerce')
        
        # Add timezone based on coordinates
        df_clean['timezone'] = df_clean.apply(
            lambda row: detect_timezone(row['Lat'], row['Long']), axis=1
        )
        
        df_clean['provider'] = df_clean.apply(self._determine_provider, axis=1)
        df_clean['provider'] = df_clean.apply(self._determine_provider, axis=1)
        df_clean['provider'] = df_clean.apply(self._determine_provider, axis=1)
        df_clean['provider'] = df_clean.apply(self._determine_provider, axis=1)
        df_clean['provider'] = df_clean.apply(self._determine_provider, axis=1)
        df_clean['provider'] = df_clean.apply(self._determine_provider, axis=1)
        df_clean['name'] = df_clean['Site/Cabang'].apply(self._create_router_name)
        df_clean['ip'] = df_clean.apply(self._get_primary_ip, axis=1)
        
        return df_clean
    
    def _determine_provider(self, row):
        ip_lintas = str(row['IP Lintas']).strip()
    def _create_router_name(self, site_name):
        return f"router-{site_name.replace('/', '_').replace(' ', '_').lower()}"
        ip_icon = str(row['IP ICON']).strip()
        
        if ip_lintas and ip_icon:
            return 'both'
        elif ip_lintas:
            return 'lintasarta'
        elif ip_icon:
            return 'icon'
        else:
            return 'unknown'
    def _create_router_name(self, site_name):
        return f"router-{site_name.replace('/', '_').replace(' ', '_').lower()}"
    def _import_to_database(self, df):
        conn = self.db_manager.get_connection()
        
        inserted_count = 0
        updated_count = 0
        
        for _, row in df.iterrows():
            existing = conn.execute(
                'SELECT * FROM routers WHERE (name = ? AND ip = ? AND provider = ?)',
                (row['name'], row['ip'], row['provider'])
            ).fetchone()
            
            if existing:
                conn.execute('''
                    UPDATE routers 
                    SET site = ?, name = ?, ip = ?, provider = ?, 
                        access_type = ?, nojar_cpe_versa = ?, nojar_starlink = ?,
                        latitude = ?, longitude = ?, timezone = ?, pic_name = ?, 
                        pic_phone = ?, pic_provider_phone = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE name = ? AND ip = ? AND provider = ?
                ''', (
                    row['Site/Cabang'], row['name'], row['ip'], row['provider'],
                    row['Access Type'], row['Nojar Versa'], row['Nojar Starlink'],
                    row['Lat'], row['Long'], row['timezone'], row['Nama PIC'], row['No WA PIC'],
                    row['No WA Provider'],
                    row['name'], row['ip'], row['provider']
                ))
                updated_count += 1
            else:
                conn.execute('''
                    INSERT INTO routers 
                    (site, name, ip, provider, access_type, 
                     nojar_cpe_versa, nojar_starlink, latitude, longitude, timezone,
                     pic_name, pic_phone, pic_provider_phone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row['Site/Cabang'], row['name'], row['ip'], row['provider'],
                    row['Access Type'], row['Nojar Versa'], row['Nojar Starlink'],
                    row['Lat'], row['Long'], row['timezone'], row['Nama PIC'], row['No WA PIC'],
                    row['No WA Provider']
                ))
                inserted_count += 1
        
        conn.commit()
        conn.close()
        
        return {
            "inserted": inserted_count,
            "updated": updated_count,
            "total": len(df)
        }
    
    def _create_router_name(self, site_name):
def detect_timezone(lat, lon):
    """Detect timezone from coordinates"""
    if pd.isna(lat) or pd.isna(lon):
        return 'Asia/Makassar'  # Default WITA (Bank Kalsel)
    if lon < 105:
        return 'Asia/Jakarta'      # WIB (UTC+7)
    elif lon < 125:
    def _import_to_database(self, df):
        conn = self.db_manager.get_connection()
        
        inserted_count = 0
        updated_count = 0
        
        for _, row in df.iterrows():
            existing = conn.execute(
                'SELECT * FROM routers WHERE (name = ? AND ip = ? AND provider = ?)',
                (row['name'], row['ip'], row['provider'])
            ).fetchone()
            
            if existing:
                conn.execute('''
                    UPDATE routers 
                    SET site = ?, name = ?, ip = ?, provider = ?, 
                        access_type = ?, nojar_cpe_versa = ?, nojar_starlink = ?,
                        latitude = ?, longitude = ?, timezone = ?, pic_name = ?, 
                        pic_phone = ?, pic_provider_phone = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE name = ? AND ip = ? AND provider = ?
                ''', (
                    row['Site/Cabang'], row['name'], row['ip'], row['provider'],
                    row['Access Type'], row['Nojar Versa'], row['Nojar Starlink'],
                    row['Lat'], row['Long'], row['timezone'], row['Nama PIC'], row['No WA PIC'],
                    row['No WA Provider'],
                    row['name'], row['ip'], row['provider']
                ))
                updated_count += 1
            else:
                conn.execute('''
                    INSERT INTO routers 
                    (site, name, ip, provider, access_type, 
                     nojar_cpe_versa, nojar_starlink, latitude, longitude, timezone,
                     pic_name, pic_phone, pic_provider_phone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row['Site/Cabang'], row['name'], row['ip'], row['provider'],
                    row['Access Type'], row['Nojar Versa'], row['Nojar Starlink'],
                    row['Lat'], row['Long'], row['timezone'], row['Nama PIC'], row['No WA PIC'],
                    row['No WA Provider']
                ))
                inserted_count += 1
        
        conn.commit()
        conn.close()
        
        return {
            "inserted": inserted_count,
            "updated": updated_count,
            "total": len(df)
        }
        return 'Asia/Makassar'     # WITA (UTC+8)
    else:
        return 'Asia/Jayapura'     # WIT (UTC+9)
        return f"router-{site_name.replace('/', '_').replace(' ', '_').lower()}"
    
    def _get_primary_ip(self, row):
        ip_lintas = str(row['IP Lintas']).strip()
        ip_icon = str(row['IP ICON']).strip()
        
        if ip_lintas:
            return ip_lintas
        elif ip_icon:
            return ip_icon
        else:
            return ''
    
    def _import_to_database(self, df):
                    access_type = ?, nojar_cpe_versa = ?, nojar_starlink = ?,
                    latitude = ?, longitude = ?, timezone = ?, pic_name = ?, 
                    pic_phone = ?, pic_provider_phone = ?, updated_at = CURRENT_TIMESTAMP
                WHERE name = ? AND ip = ? AND provider = ?
            ''', (
                row['Site/Cabang'], row['name'], row['ip'], row['provider'],
                row['Access Type'], row['Nojar Versa'], row['Nojar Starlink'],
                row['Lat'], row['Long'], row['timezone'], row['Nama PIC'], row['No WA PIC'],
                row['No WA Provider'],
                row['name'], row['ip'], row['provider']
            ))
        conn = self.db_manager.get_connection()
        
        inserted_count = 0
        updated_count = 0
                    (site, name, ip, provider, access_type, 
                     nojar_cpe_versa, nojar_starlink, latitude, longitude, timezone,
                     pic_name, pic_phone, pic_provider_phone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row['Site/Cabang'], row['name'], row['ip'], row['provider'],
                    row['Access Type'], row['Nojar Versa'], row['Nojar Starlink'],
                    row['Lat'], row['Long'], row['timezone'], row['Nama PIC'], row['No WA PIC'],
                    row['No WA Provider']
                ))
        
        for _, row in df.iterrows():
            existing = conn.execute(
                'SELECT * FROM routers WHERE (name = ? AND ip = ? AND provider = ?)',
                (row['name'], row['ip'], row['provider'])
            ).fetchone()
            
            if existing:
                conn.execute('''
                    UPDATE routers 
                    SET site = ?, name = ?, ip = ?, provider = ?, 
                        access_type = ?, nojar_cpe_versa = ?, nojar_starlink = ?,
                        latitude = ?, longitude = ?, pic_name = ?, 
                        pic_phone = ?, pic_provider_phone = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE name = ? AND ip = ? AND provider = ?
                ''', (
                    row['Site/Cabang'], row['name'], row['ip'], row['provider'],
                    row['Access Type'], row['Nojar Versa'], row['Nojar Starlink'],
                    row['Lat'], row['Long'], row['Nama PIC'], row['No WA PIC'],
                    row['No WA Provider'],
                    row['name'], row['ip'], row['provider']
                ))
                updated_count += 1
            else:
                conn.execute('''
                    INSERT INTO routers 
                    (site, name, ip, provider, access_type, 
                     nojar_cpe_versa, nojar_starlink, latitude, longitude,
                     pic_name, pic_phone, pic_provider_phone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row['Site/Cabang'], row['name'], row['ip'], row['provider'],
                    row['Access Type'], row['Nojar Versa'], row['Nojar Starlink'],
                    row['Lat'], row['Long'], row['Nama PIC'], row['No WA PIC'],
                    row['No WA Provider']
                ))
                inserted_count += 1
        
        conn.commit()
        conn.close()
        
        return {
            "inserted": inserted_count,
            "updated": updated_count,
            "total": len(df)
        }

def main():
    importer = BranchImporter()
    result = importer.import_branches_from_excel("branches_data.xlsx")
    print(f"Import result: {result}")

if __name__ == "__main__":
    main()
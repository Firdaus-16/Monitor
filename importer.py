#!/usr/bin/env python3
"""Enterprise SD-WAN Monitoring System - Importer Module"""

import pandas as pd
import logging
import os
from database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def detect_timezone(lat, lon):
    """Detect timezone from coordinates"""
    if pd.isna(lat) or pd.isna(lon):
        return 'Asia/Makassar'
    try:
        lon_value = float(lon)
    except (TypeError, ValueError):
        return 'Asia/Makassar'
    if lon_value < 105:
        return 'Asia/Jakarta'
    elif lon_value < 125:
        return 'Asia/Makassar'
    else:
        return 'Asia/Jayapura'

class BranchImporter:
    COLUMN_MAPPING = COLUMN_MAPPING

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
            df = self._normalize_columns(df)

            required = ['site', 'ip_lintas', 'ip_icon', 'access_type']
            missing = [col for col in required if col not in df.columns]
            if missing:
                return {"success": False, "error": f"Missing columns: {missing}"}

            cleaned_data = self._clean_excel_data(df)
            import_result = self._import_to_database(cleaned_data)

            logger.info(f"Import completed: {import_result}")
            return {"success": True, "results": import_result}

        except Exception as e:
            logger.error(f"Excel import failed: {e}")
            return {"success": False, "error": str(e)}

    def _normalize_columns(self, df):
        """Normalize column names based on mapping"""
        normalized = {}
        for standard, variants in self.COLUMN_MAPPING.items():
            variant_set = {str(variant).strip().lower() for variant in variants}
            for col in df.columns:
                if str(col).strip().lower() in variant_set:
                    normalized[col] = standard
                    break
        if normalized:
            df = df.rename(columns=normalized)
        return df

    def _cell(self, row, key):
        """Safely read a cell value as a stripped string."""
        if key not in row:
            return ''
        value = row[key]
        if pd.isna(value):
            return ''
        text = str(value).strip()
        if text.lower() in ('nan', 'none', 'nat', '<na>'):
            return ''
        return text

    def _clean_excel_data(self, df):
        df_clean = self._normalize_columns(df.copy())

        # Ensure the normalized schema is complete even for partial Excel files.
        for standard in self.COLUMN_MAPPING:
            if standard not in df_clean.columns:
                if standard in ('lat', 'long'):
                    df_clean[standard] = pd.NA
                else:
                    df_clean[standard] = ''

        site_mask = df_clean['site'].apply(lambda value: '' if pd.isna(value) else str(value).strip())
        df_clean = df_clean[site_mask != '']

        string_columns = [col for col in self.COLUMN_MAPPING if col not in ('lat', 'long')]
        for col in string_columns:
            if col in df_clean.columns:
                df_clean[col] = df_clean[col].fillna('').astype(str).str.strip()
                df_clean[col] = df_clean[col].replace({'nan': '', 'None': '', '<NA>': ''})

        if 'lat' in df_clean.columns:
            df_clean['lat'] = pd.to_numeric(df_clean['lat'], errors='coerce')
        if 'long' in df_clean.columns:
            df_clean['long'] = pd.to_numeric(df_clean['long'], errors='coerce')

        df_clean['timezone'] = df_clean.apply(
            lambda row: detect_timezone(row['lat'], row['long']), axis=1
        )
        df_clean['provider'] = df_clean.apply(self._determine_provider, axis=1)
        df_clean['name'] = df_clean['site'].apply(self._create_router_name)
        df_clean['ip'] = df_clean.apply(self._get_primary_ip, axis=1)

        return df_clean

    def _determine_provider(self, row):
        ip_lintas = self._cell(row, 'ip_lintas')
        ip_icon = self._cell(row, 'ip_icon')

        if ip_lintas and ip_icon:
            return 'both'
        elif ip_lintas:
            return 'lintasarta'
        elif ip_icon:
            return 'icon'
        else:
            return 'unknown'

    def _create_router_name(self, site_name):
        site_name = '' if pd.isna(site_name) else str(site_name)
        return f"router-{site_name.replace('/', '_').replace(' ', '_').lower()}"

    def _get_primary_ip(self, row):
        ip_lintas = self._cell(row, 'ip_lintas')
        ip_icon = self._cell(row, 'ip_icon')

        if ip_lintas:
            return ip_lintas
        elif ip_icon:
            return ip_icon
        else:
            return ''

    def _import_to_database(self, df):
        if hasattr(self.db_manager, 'init_db'):
            try:
                self.db_manager.init_db()
            except Exception:
                pass

        conn = self.db_manager.get_connection()

        inserted_count = 0
        updated_count = 0

        for _, row in df.iterrows():
            name = self._cell(row, 'name')
            ip = self._cell(row, 'ip')
            provider = self._cell(row, 'provider')

            existing = conn.execute(
                'SELECT * FROM routers WHERE (name = ? AND ip = ? AND provider = ?)',
                (name, ip, provider)
            ).fetchone()

            site = self._cell(row, 'site')
            access_type = self._cell(row, 'access_type')
            nojar_versa = self._cell(row, 'nojar_versa')
            nojar_starlink = self._cell(row, 'nojar_starlink')

            latitude = row['lat'] if 'lat' in row else None
            longitude = row['long'] if 'long' in row else None
            if pd.isna(latitude):
                latitude = None
            if pd.isna(longitude):
                longitude = None

            timezone = self._cell(row, 'timezone') or 'Asia/Makassar'
            router_versa_name = self._cell(row, 'router_versa_name')
            router_model = self._cell(row, 'router_model')
            router_versa_regist = self._cell(row, 'router_versa_regist')
            psu_regist = self._cell(row, 'psu_regist')
            pic_name = self._cell(row, 'pic_name')
            pic_phone = self._cell(row, 'pic_phone')
            pic_provider_phone = self._cell(row, 'pic_provider_phone')

            if existing:
                conn.execute('''
                    UPDATE routers
                    SET site = ?, name = ?, ip = ?, provider = ?,
                        access_type = ?, nojar_cpe_versa = ?, nojar_starlink = ?,
                        latitude = ?, longitude = ?, timezone = ?,
                        router_versa_name = ?, router_model = ?, router_versa_regist = ?, psu_regist = ?,
                        pic_name = ?, pic_phone = ?, pic_provider_phone = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE name = ? AND ip = ? AND provider = ?
                ''', (
                    site, name, ip, provider,
                    access_type, nojar_versa, nojar_starlink,
                    latitude, longitude, timezone,
                    router_versa_name, router_model, router_versa_regist, psu_regist,
                    pic_name, pic_phone, pic_provider_phone,
                    name, ip, provider
                ))
                updated_count += 1
            else:
                conn.execute('''
                    INSERT INTO routers
                    (site, name, ip, provider, access_type,
                     nojar_cpe_versa, nojar_starlink, latitude, longitude, timezone,
                     router_versa_name, router_model, router_versa_regist, psu_regist,
                     pic_name, pic_phone, pic_provider_phone)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    site, name, ip, provider,
                    access_type, nojar_versa, nojar_starlink,
                    latitude, longitude, timezone,
                    router_versa_name, router_model, router_versa_regist, psu_regist,
                    pic_name, pic_phone, pic_provider_phone
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

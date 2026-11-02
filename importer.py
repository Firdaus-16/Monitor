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

    def import_branches_from_excel(self, filepath):
        if not os.path.exists(filepath):
            return {"success": False, "error": f"File not found: {filepath}"}

        try:
            df = pd.read_excel(filepath, dtype=str)
            df = self._normalize_columns(df)

            required_check = ['site']
            missing = [col for col in required_check if col not in df.columns]
            if missing:
                return {"success": False, "error": f"Missing required column: {missing}"}

            routers_to_import = self._prepare_routers(df)
            import_result = self._import_to_database(routers_to_import)

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

    def _slugify(self, text):
        return str(text).replace('/', '_').replace(' ', '_').replace('-', '_').lower()

    def _prepare_routers(self, df):
        """Extract individual router items (1 or 2 per branch row for dual provider)."""
        router_list = []
        for _, row in df.iterrows():
            site = self._cell(row, 'site')
            if not site:
                continue

            ip_lintas = self._cell(row, 'ip_lintas')
            ip_icon = self._cell(row, 'ip_icon')
            access_type = self._cell(row, 'access_type') or 'SD-WAN'
            nojar_versa = self._cell(row, 'nojar_versa')
            nojar_starlink = self._cell(row, 'nojar_starlink')

            # Latitude and Longitude parsing
            try:
                lat = float(row['lat']) if 'lat' in row and not pd.isna(row['lat']) else None
            except (ValueError, TypeError):
                lat = None
            try:
                lon = float(row['long']) if 'long' in row and not pd.isna(row['long']) else None
            except (ValueError, TypeError):
                lon = None

            timezone = detect_timezone(lat, lon)
            router_versa_name = self._cell(row, 'router_versa_name')
            router_model = self._cell(row, 'router_model')
            router_versa_regist = self._cell(row, 'router_versa_regist')
            psu_regist = self._cell(row, 'psu_regist')
            pic_name = self._cell(row, 'pic_name')
            pic_phone = self._cell(row, 'pic_phone')
            pic_provider_phone = self._cell(row, 'pic_provider_phone')

            site_slug = self._slugify(site)

            # 1. Lintasarta Router
            if ip_lintas:
                router_list.append({
                    'site': site,
                    'name': f"router-{site_slug}-lintasarta",
                    'ip': ip_lintas,
                    'provider': 'lintasarta',
                    'access_type': access_type,
                    'nojar_cpe_versa': nojar_versa,
                    'nojar_starlink': nojar_starlink,
                    'latitude': lat,
                    'longitude': lon,
                    'timezone': timezone,
                    'router_versa_name': router_versa_name,
                    'router_model': router_model,
                    'router_versa_regist': router_versa_regist,
                    'psu_regist': psu_regist,
                    'pic_name': pic_name,
                    'pic_phone': pic_phone,
                    'pic_provider_phone': pic_provider_phone
                })

            # 2. ICON / Starlink Router
            if ip_icon:
                router_list.append({
                    'site': site,
                    'name': f"router-{site_slug}-icon",
                    'ip': ip_icon,
                    'provider': 'icon',
                    'access_type': access_type,
                    'nojar_cpe_versa': nojar_versa,
                    'nojar_starlink': nojar_starlink,
                    'latitude': lat,
                    'longitude': lon,
                    'timezone': timezone,
                    'router_versa_name': router_versa_name,
                    'router_model': router_model,
                    'router_versa_regist': router_versa_regist,
                    'psu_regist': psu_regist,
                    'pic_name': pic_name,
                    'pic_phone': pic_phone,
                    'pic_provider_phone': pic_provider_phone
                })

        return router_list

    def _import_to_database(self, routers):
        if hasattr(self.db_manager, 'init_db'):
            try:
                self.db_manager.init_db()
            except Exception:
                pass

        conn = self.db_manager.get_connection()
        inserted_count = 0
        updated_count = 0

        for r in routers:
            existing = conn.execute(
                'SELECT id FROM routers WHERE (name = ? AND ip = ? AND provider = ?)',
                (r['name'], r['ip'], r['provider'])
            ).fetchone()

            if existing:
                conn.execute('''
                    UPDATE routers
                    SET site = ?, access_type = ?, nojar_cpe_versa = ?, nojar_starlink = ?,
                        latitude = ?, longitude = ?, timezone = ?,
                        router_versa_name = ?, router_model = ?, router_versa_regist = ?, psu_regist = ?,
                        pic_name = ?, pic_phone = ?, pic_provider_phone = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE name = ? AND ip = ? AND provider = ?
                ''', (
                    r['site'], r['access_type'], r['nojar_cpe_versa'], r['nojar_starlink'],
                    r['latitude'], r['longitude'], r['timezone'],
                    r['router_versa_name'], r['router_model'], r['router_versa_regist'], r['psu_regist'],
                    r['pic_name'], r['pic_phone'], r['pic_provider_phone'],
                    r['name'], r['ip'], r['provider']
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
                    r['site'], r['name'], r['ip'], r['provider'], r['access_type'],
                    r['nojar_cpe_versa'], r['nojar_starlink'], r['latitude'], r['longitude'], r['timezone'],
                    r['router_versa_name'], r['router_model'], r['router_versa_regist'], r['psu_regist'],
                    r['pic_name'], r['pic_phone'], r['pic_provider_phone']
                ))
                inserted_count += 1

        conn.commit()
        conn.close()

        return {
            "inserted": inserted_count,
            "updated": updated_count,
            "total_routers": len(routers)
        }

def main():
    importer = BranchImporter()
    result = importer.import_branches_from_excel("branches_data.xlsx")
    print(f"Import result: {result}")

if __name__ == "__main__":
    main()

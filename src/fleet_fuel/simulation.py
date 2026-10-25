"""Reproducible fictional fleet, physical ledger and imperfect observations."""
from __future__ import annotations
import hashlib, json, math, random
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
VERSION = '1.0.0'
LA = ZoneInfo('America/Los_Angeles')
UTC = timezone.utc
START = datetime(2025, 1, 1, tzinfo=LA)
END = datetime(2025, 7, 1, tzinfo=LA)
GALLON = 3.785411784
MILE = 1.609344
DERIVED = {'fuel_paired_interval', 'fuel_weekly_metric', 'fuel_inventory_balance', 'fuel_report_run'}

def stamp(v):
    return v.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')

def parse(v):
    return datetime.fromisoformat(v.replace('Z', '+00:00'))

def rounded(v):
    return round(v, 6)

def sub_seed(seed, *tokens):
    return int.from_bytes(hashlib.sha256('\x1f'.join(map(str, (seed, *tokens))).encode('utf-8')).digest()[:16], 'big')

def week_start(v):
    v = v.astimezone(LA)
    return datetime(v.year, v.month, v.day, tzinfo=LA) - timedelta(days=v.weekday())

def output_id(tenant, when, view='revised'):
    return f'{tenant}-FUEL-{week_start(when):%Y%m%d}-{view}'

def file_digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def _line(h, row):
    h.write(json.dumps(row, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')

def build_plan(seed=20261021):
    trips = []
    for ti in range(1, 4):
        for vi in range(1, 11):
            tenant = f'T{ti:02}'
            vehicle = f'{tenant}-V{vi:02}'
            for j in range(60):
                tid = f'{vehicle}-TR{j + 1:03}'
                rng = random.Random(sub_seed(seed, 'trip', tid))
                start = START + timedelta(days=3 * j + (vi - 1) % 3, hours=6 + (vi - 1) % 4)
                if ti == vi == 1 and j == 20:
                    start = datetime(2025, 3, 2, 23, 30, tzinfo=LA)
                if ti == vi == 1 and j == 22:
                    start = datetime(2025, 3, 9, 1, 30, tzinfo=LA)
                minutes = rng.choice([90, 120, 150, 180])
                idle = rng.randint(8, 18)
                pto = rng.choice([0, 0, 5, 10, 15])
                if ti == 1 and vi == 3 and (start.month >= 4):
                    idle += 20
                moving = minutes - idle - pto
                task = 'linehaul' if (j + vi) % 3 else 'regional_delivery'
                load = rng.randint(4500, 21000) if task == 'linehaul' else rng.randint(1500, 10000)
                speed = rng.uniform(58, 83) if task == 'linehaul' else rng.uniform(38, 60)
                end = start.astimezone(UTC) + timedelta(minutes=minutes)
                driver = vi if j < 30 or vi > 5 else vi + 10
                trips.append(dict(trip_id=tid, task_id=tid, tenant_id=tenant, vehicle_id=vehicle, driver_id=f'{tenant}-R{driver:02}', route_id=f'ROUTE-{(j + vi + ti) % 12 + 1:02}', start_at=stamp(start), end_at=stamp(end), start=stamp(start), end=stamp(end), distance_km=rounded(moving * speed / 60), expected_seconds=minutes * 60, task_type=task, load_kg=load, pto_seconds=pto * 60, idle_seconds=idle * 60, moving_seconds=moving * 60, sequence=j + 1, origin_type='synthetic'))
    return trips

def select_trips(plan, profile, seed=20261021):
    if profile == 'full':
        return {x['trip_id'] for x in plan}
    if profile not in {'smoke', 'small'}:
        raise ValueError('profile must be full or smoke')
    ids = {x['trip_id'] for x in plan if x['sequence'] in {1, 30, 60}}
    ids.update(['T01-V01-TR021', 'T01-V01-TR023', 'T01-V01-TR016', 'T02-V02-TR002', 'T03-V10-TR032', 'T03-V09-TR032', 'T01-V02-TR017', 'T01-V03-TR020', 'T02-V03-TR040', 'T03-V08-TR036'])
    return ids

class SourceWriter:

    def __init__(self, root, contract, created):
        self.root = root
        self.created = created
        self.tables = {x['name']: x for x in contract['tables']}
        self.fields = defaultdict(list)
        for f in contract['fields']:
            self.fields[f['table']].append(f)
        folder = root / 'data/raw/tables'
        folder.mkdir(parents=True, exist_ok=True)
        self.files = {name: (folder / (name + '.jsonl')).open('w') for name in self.tables if name not in DERIVED}
        self.events = (root / 'data/raw/events.jsonl').open('w')
        self.counts = Counter()
        self.attempts = 0
        self.first = None

    def emit(self, table, values, when=START, available=None, scenario='FUEL-NORMAL', source_id=None, version='1', states=None, evidence='scenario-1.0.0; complete operational ledger', transport=False):
        row = {f['name']: values.get(f['name']) for f in self.fields[table]}
        pk = {k: row[k] for k in self.tables[table]['primary_key']}
        key = '|'.join(map(str, pk.values()))
        pid = 'P-' + hashlib.sha256((table + '|' + key).encode()).hexdigest()[:24]
        event = stamp(when) if isinstance(when, datetime) else when
        avail = stamp(available) if isinstance(available, datetime) else available or event
        if 'provenance_id' in row:
            row['provenance_id'] = pid
        self.counts[table] += 1
        _line(self.files[table], row)
        if 'provenance_id' in row and table != 'provenance_record':
            vs = {f'{table}.{k}': {'state': 'not_applicable', 'reason': 'Not applicable to this source record'} for k, v in row.items() if v is None}
            vs.update(states or {})
            local = parse(event).astimezone(LA)
            p = dict(provenance_id=pid, source_system_id='fictional_fleet_operations_v1', source_record_id=source_id or key, record_version=version, record_state=row.get('record_state', 'active'), event_time=event, available_time=avail, retrieved_at=self.created, extract_as_of=self.created if table == 'fuel_reference_case' else '2025-07-10T23:59:59Z', raw_record_reference=f'data/raw/tables/{table}.jsonl#line={self.counts[table]}', origin_type='synthetic', source_dataset_id='fleet-fuel-sample-v1.0.0', synthetic_scenario_id=scenario, value_states=vs, source_timezone='America/Los_Angeles', source_utc_offset_minutes=int(local.utcoffset().total_seconds() / 60), tenant_id=row.get('tenant_id'), field_origins={}, availability_basis='simulated', availability_evidence=evidence, canonical_table=table, canonical_record_key=pk, parent_provenance_ids=[])
            self.counts['provenance_record'] += 1
            _line(self.files['provenance_record'], p)
        if transport:
            e = dict(event_id=source_id or key, revision=int(version), available_time=avail, event_time=event, tenant_id=row['tenant_id'], table=table, payload=row)
            _line(self.events, e)
            self.attempts += 1
            if self.first is None:
                self.first = e
            if self.counts[table] % 10007 == 0:
                _line(self.events, e)
                self.attempts += 1
        return row

    def close(self):
        if self.first:
            bad = dict(self.first)
            bad['event_id'] = 'TRANSPORT-MISSING-KEY'
            bad['payload'] = dict(bad['payload'])
            del bad['payload']['counter_observation_id']
            _line(self.events, bad)
            self.attempts += 1
        self.events.close()
        for f in self.files.values():
            f.close()

def _device(tenant, vi, when):
    if tenant == 'T01' and vi == 1 and (when >= datetime(2025, 4, 1, tzinfo=LA)):
        return 'T01-D11'
    if tenant == 'T02' and vi == 5 and (when >= datetime(2025, 5, 1, tzinfo=LA)):
        return 'T02-D11'
    return f'{tenant}-D{vi:02}'

def _boundaries():
    dates = [START]
    d = week_start(START) + timedelta(days=7)
    while d < END:
        dates.append(d)
        d += timedelta(days=7)
    return dates + [END]

def generate(root: Path, profile='full', seed=20261021):
    root = Path(root)
    contract = json.loads((root / 'contracts/da_e01_contract.json').read_text())
    config = json.loads((root / 'config/simulation.json').read_text())
    created = config['dataset_created_at']
    w = SourceWriter(root, contract, created)
    capacity = float(config['tank_capacity_l'])
    initial_inventory = float(config['initial_inventory_l'])
    modulus_l = float(config['fuel_modulus_l'])
    rates = config['fuel_efficiency_l_per_km']
    op = root / 'data/raw/operations'
    op.mkdir(parents=True, exist_ok=True)
    expected = root / 'validation/expected'
    expected.mkdir(parents=True, exist_ok=True)
    plan = build_plan(seed)
    selected = select_trips(plan, profile, seed)
    selected_plan = [x for x in plan if x['trip_id'] in selected]
    for name, rows in [('trip_plan', plan), ('trips', selected_plan)]:
        with (op / (name + '.jsonl')).open('w') as h:
            for row in rows:
                _line(h, row)
    with (op / 'drivers.jsonl').open('w') as h:
        for ti in range(1, 4):
            for ri in range(1, 16):
                _line(h, dict(tenant_id=f'T{ti:02}', driver_id=f'T{ti:02}-R{ri:02}', display_name=f'Fictional driver {ti}-{ri:02}', valid_from=stamp(START), valid_to=stamp(END), origin_type='synthetic'))
    cities = [('CA', 34.05, -118.24), ('CA', 33.95, -117.4), ('CA', 35.37, -119.02), ('CA', 36.74, -119.78), ('NV', 36.17, -115.14), ('NV', 35.98, -114.83), ('NV', 39.53, -119.81), ('NV', 38.94, -119.98), ('AZ', 33.45, -112.07), ('AZ', 32.22, -110.97), ('AZ', 35.2, -111.65), ('AZ', 32.69, -114.63)]
    (op / 'facilities.json').write_text(json.dumps([dict(facility_id=f'SITE-{i + 1:02}', state=s, latitude=lat, longitude=lon, name=f'Fictional depot {i + 1:02}', origin_type='synthetic') for i, (s, lat, lon) in enumerate(cities)], indent=2) + '\n')
    (op / 'routes.json').write_text(json.dumps([dict(route_id=f'ROUTE-{i + 1:02}', origin_facility_id=f'SITE-{i + 1:02}', destination_facility_id=f'SITE-{(i + 1) % 12 + 1:02}', geometry_status='abstract_synthetic_route; no road-network travel assertion') for i in range(12)], indent=2) + '\n')
    for ti in range(1, 4):
        tenant = f'T{ti:02}'
        w.emit('core_tenant', dict(tenant_id=tenant, tenant_name=f'Fictional Fleet {ti}', report_timezone='America/Los_Angeles', base_currency='USD'))
        for di in range(1, 13):
            w.emit('core_device', dict(tenant_id=tenant, device_id=f'{tenant}-D{di:02}', device_model='SIM-ELD-01'))
        for si in range(12):
            station = f'{tenant}-ST{si + 1:02}'
            w.emit('fuel_station', dict(tenant_id=tenant, station_version_id=station + '-v1', station_country='US', station_state=cities[si][0], station_id=station))
        for state in ['CA', 'NV', 'AZ']:
            w.emit('fuel_region_mapping', dict(tenant_id=tenant, region_mapping_id=f'{tenant}-{state}-v1', region_mapping_version='synthetic-regions-1', country_code='US', state_code=state, market_region='CA' if state == 'CA' else 'WEST_COAST_EX_CA', valid_from=stamp(START), valid_to=stamp(END)))
        for vi in range(1, 11):
            vehicle = f'{tenant}-V{vi:02}'
            vin = f'SYNTHETIC{ti:02}{vi:06}'
            w.emit('core_vehicle', dict(tenant_id=tenant, vehicle_id=vehicle, vin_raw=vin, vin=vin, vehicle_class='heavy_truck' if vi < 9 else 'medium_truck', fuel_type='diesel'))
            w.emit('fuel_vehicle_context', dict(tenant_id=tenant, vehicle_context_id=vehicle + '-CTX1', vehicle_source_id=vehicle + '-OPS', vehicle_active_from=stamp(START), vehicle_active_to=stamp(END), operating_timezone='America/Los_Angeles', day_boundary_local='00:00:00', vehicle_id=vehicle))
            intervals = [(START, END, f'{tenant}-D{vi:02}')]
            if tenant == 'T01' and vi == 1:
                cut = datetime(2025, 4, 1, tzinfo=LA)
                intervals = [(START, cut, 'T01-D01'), (cut, END, 'T01-D11')]
            if tenant == 'T02' and vi == 5:
                cut = datetime(2025, 5, 1, tzinfo=LA)
                intervals = [(START, cut, 'T02-D05'), (cut, END, 'T02-D11')]
            if tenant == 'T03' and vi == 10:
                a = datetime(2025, 4, 4, tzinfo=LA)
                b = a + timedelta(days=2)
                intervals = [(START, a, 'T03-D10'), (b, END, 'T03-D10')]
            for n, (a, b, device) in enumerate(intervals):
                w.emit('core_vehicle_device_assignment', dict(tenant_id=tenant, assignment_id=f'{vehicle}-ASG{n + 1}', vehicle_id=vehicle, device_id=device, valid_from=stamp(a), valid_to=stamp(b), known_from=stamp(START - timedelta(days=1)), known_to=None, valid_to_state='known', known_to_state='open', resolution_status='resolved'), a)
            if tenant == 'T03' and vi == 9:
                a = datetime(2025, 4, 4, tzinfo=LA)
                b = a + timedelta(days=2)
                w.emit('core_vehicle_device_assignment', dict(tenant_id=tenant, assignment_id=f'{vehicle}-ASG-CONFLICT', vehicle_id='T03-V08', device_id='T03-D09', valid_from=stamp(a), valid_to=stamp(b), known_from=stamp(a), known_to=None, valid_to_state='known', known_to_state='open', resolution_status='ambiguous'), a, scenario='IDENTITY-OVERLAP')
            w.emit('fuel_card_assignment', dict(tenant_id=tenant, card_assignment_id=vehicle + '-CARD-ASG', card_vehicle_from=stamp(START), card_vehicle_to=stamp(END), vehicle_id=vehicle, fuel_card_id=vehicle + '-CARD', known_from=stamp(START - timedelta(days=1)), known_to=None))
            w.emit('fuel_tank_scope', dict(tenant_id=tenant, tank_scope_version_id=vehicle + '-TANK-V1', inventory_tank_scope_id=vehicle + '-TANK', tank_capacity_l=capacity, vehicle_id=vehicle))
            for kind in ['fuel_total', 'odometer']:
                modulus = rounded(modulus_l / GALLON) if tenant == 'T02' and vi == 2 and (kind == 'fuel_total') else None
                unit = ('US_gal' if vi % 2 == 0 else 'L') if kind == 'fuel_total' else 'mile' if vi % 2 == 0 else 'km'
                w.emit('fuel_signal_definition', dict(tenant_id=tenant, signal_definition_id=vehicle + '-' + kind, source_ecu_id=vehicle + '-ECU', signal_definition_version='sample-1', signal_kind=kind, signal_unit=unit, signal_resolution=1e-06, counter_modulus=modulus, firmware_version='SIM-1.0', ecu_configuration='FICTIONAL-DIESEL-CONFIG', signal_protocol='synthetic', source_signal_locator='decoded_json.' + ('fuel_total_raw' if kind == 'fuel_total' else 'odometer_raw'), valid_from=stamp(START), valid_to=stamp(END)))
    first_week = week_start(START)
    for tenant in ['T01', 'T02', 'T03']:
        for n in range(28):
            day = first_week + timedelta(days=7 * n)
            for region, base in [('CA', 4.85), ('WEST_COAST_EX_CA', 4.15)]:
                price = round(base + 0.16 * math.sin(n / 3.7) - 0.007 * n, 4)
                w.emit('fuel_market_price', dict(tenant_id=tenant, market_price_version_id=f'{tenant}-SYN-{region}-{day:%Y%m%d}', market_week_price=price, market_region=region, eia_series_id=None, price_observation_date=day.date().isoformat(), price_published_at=stamp(day + timedelta(hours=8)), price_retrieved_at=created, price_snapshot_ref='config/simulation.json#market_price', price_method_version='synthetic-price-1', origin_label='synthetic', publication_precision='timestamp'), day, day + timedelta(hours=8), scenario='SYNTHETIC-PRICE')
    control = defaultdict(lambda: dict(amount=0.0, quantity=0.0, lines=0))
    latent = []
    injections = []
    physical = []
    for ti in range(1, 4):
        for vi in range(1, 11):
            tenant = f'T{ti:02}'
            vehicle = f'{tenant}-V{vi:02}'
            tank = initial_inventory
            physical_fuel = 0.0
            odo = 200000.0 + ti * 10000 + vi * 500
            counter = 3950.0 if tenant == 'T02' and vi == 2 else 10000.0 + vi * 100
            ledger = [(START.astimezone(UTC), tank, counter, odo)]
            for trip in [x for x in plan if x['vehicle_id'] == vehicle]:
                j = trip['sequence'] - 1
                start = parse(trip['start_at'])
                end = parse(trip['end_at'])
                local = start.astimezone(LA)
                chosen = trip['trip_id'] in selected
                rng = random.Random(sub_seed(seed, 'physics', trip['trip_id']))
                target = 450.0 + 20 * (j % 5)
                qty = min(max(12.0, target - tank), capacity - tank)
                tank += qty
                station_idx = (vi + j) % 12
                state = cities[station_idx][0]
                wn = (week_start(start).date() - first_week.date()).days // 7
                price = (4.85 if state == 'CA' else 4.15) + 0.16 * math.sin(wn / 3.7) - 0.007 * wn + rng.uniform(-0.18, 0.23)
                tax = round(qty * 0.12, 2)
                discount = round(qty * 0.008, 2)
                net = round(qty / GALLON * price, 2)
                subtotal = round(net - tax + discount, 2)
                line_id = trip['trip_id'] + '-FUEL'
                statement = f'{tenant}-STMT-{local:%Y%m}'
                posted = start + timedelta(hours=12)
                purchase = dict(tenant_id=tenant, purchase_line_id=line_id, line_version='1', purchase_id=trip['trip_id'] + '-SALE', purchase_time=stamp(start), posted_at=stamp(posted), purchase_quantity_l=rounded(qty), purchase_quantity_unit='US_gal', purchase_amount=net, purchase_fuel_type='diesel', currency='USD', fuel_subtotal=subtotal, fuel_tax_amount=tax, fuel_discount_amount=discount, extra_fee_amount=0.0, nonfuel_amount=0.0, transaction_status='posted', adjustment_type='purchase', original_purchase_line_id=None, fuel_card_id=vehicle + '-CARD', station_id=f'{tenant}-ST{station_idx + 1:02}', statement_id=statement, source_amount_basis='pretax_gross' if j % 2 else 'tax_inclusive_net_fuel', vehicle_id=vehicle, quantity_raw=rounded(qty / GALLON), record_state='active')
                correction = tenant == 'T01' and vi == 2 and (j == 16)
                if correction:
                    purchase['record_state'] = 'corrected'
                w.emit('fuel_purchase_line', purchase, start, posted, source_id=line_id)
                finalnet = net
                if correction:
                    r2 = dict(purchase)
                    r2.update(line_version='2', purchase_amount=round(net - 8, 2), fuel_discount_amount=round(discount + 8, 2), posted_at=stamp(posted + timedelta(days=5)), transaction_status='corrected', adjustment_type='correction', record_state='active')
                    w.emit('fuel_purchase_line', r2, start, posted + timedelta(days=5), source_id=line_id, version='2', scenario='TRANSACTION-CORRECTION')
                    finalnet -= 8
                    injections.append(dict(scenario_id='TRANSACTION-CORRECTION', table='fuel_purchase_line', record_id=line_id, expected='latest available line_version only; no duplicate volume'))
                ctrl = control[tenant, local.year, local.month, 'fuel']
                ctrl['amount'] += finalnet
                ctrl['quantity'] += qty
                ctrl['lines'] += 1
                w.emit('fuel_movement', dict(tenant_id=tenant, fuel_movement_id=line_id + '-MOVE', fuel_movement_at=stamp(start), fuel_movement_type='refuel', fuel_movement_quantity_l=rounded(qty), fuel_movement_reference=line_id, movement_source_scope=f'{tenant}-ST{station_idx + 1:02}', movement_destination_scope=vehicle + '-TANK', vehicle_id=vehicle), start, posted)
                if j == 10:
                    extra = dict(purchase)
                    extra.update(purchase_line_id=line_id + '-NONFUEL', purchase_quantity_l=0.0, quantity_raw=0.0, purchase_amount=18.0, purchase_fuel_type='nonfuel', fuel_subtotal=0.0, fuel_tax_amount=0.0, fuel_discount_amount=0.0, nonfuel_amount=18.0, source_amount_basis='transaction_total')
                    w.emit('fuel_purchase_line', extra, start, posted, source_id=line_id + '-NONFUEL', scenario='NONFUEL-LINE')
                    c = control[tenant, local.year, local.month, 'nonfuel']
                    c['amount'] += 18.0
                    c['lines'] += 1
                if j == 25:
                    refund = dict(purchase)
                    refund.update(purchase_line_id=line_id + '-REFUND', purchase_quantity_l=0.0, quantity_raw=0.0, purchase_amount=-6.0, fuel_subtotal=-6.0, fuel_tax_amount=0.0, fuel_discount_amount=0.0, adjustment_type='amount_refund', original_purchase_line_id=line_id, source_amount_basis='tax_inclusive_net_fuel')
                    w.emit('fuel_purchase_line', refund, start, posted, source_id=line_id + '-REFUND', scenario='AMOUNT-ONLY-REFUND')
                    ctrl['amount'] -= 6
                    ctrl['lines'] += 1
                if tenant == 'T01' and vi == 1 and (j in {12, 18}):
                    amount = 20.0 if j == 12 else 15.0
                    kind = 'transfer_in' if j == 12 else 'maintenance_drain'
                    tank += amount if j == 12 else -amount
                    w.emit('fuel_movement', dict(tenant_id=tenant, fuel_movement_id=f'{vehicle}-MOVE-{j}', fuel_movement_at=stamp(start), fuel_movement_type=kind, fuel_movement_quantity_l=amount, fuel_movement_reference=f'fictional-work-order-{j}', movement_source_scope='SITE-01' if j == 12 else vehicle + '-TANK', movement_destination_scope=vehicle + '-TANK' if j == 12 else 'SITE-01', vehicle_id=vehicle), start, scenario='KNOWN-FUEL-TRANSFER')
                if tenant == 'T03' and vi == 8 and (j == 35):
                    tank -= 10
                    w.emit('fuel_movement', dict(tenant_id=tenant, fuel_movement_id=f'{vehicle}-UNKNOWN-DRAIN', fuel_movement_at=stamp(start), fuel_movement_type='maintenance_drain', fuel_movement_quantity_l=None, fuel_movement_reference='fictional-unmetered-drain-record', movement_source_scope=vehicle + '-TANK', movement_destination_scope='SITE-09', vehicle_id=vehicle), start, scenario='UNKNOWN-MOVEMENT', states={'fuel_movement.fuel_movement_quantity_l': dict(state='unknown', reason='Drain recorded without measured volume')})
                if tenant == 'T01' and vi == 1 and (j == 15):
                    counter = 50.0
                    w.emit('fuel_counter_change', dict(tenant_id=tenant, counter_change_id=vehicle + '-FUEL-RESET', counter_change_at=stamp(start), counter_change_type='reset', counter_change_evidence='fictional ECU service log reset-1', vehicle_id=vehicle, device_id=_device(tenant, vi, start), signal_definition_id=vehicle + '-fuel_total', signal_kind='fuel_total'), start, scenario='FUEL-RESET')
                if tenant == 'T01' and vi == 1 and (j == 25):
                    odo = 150.0
                    w.emit('fuel_counter_change', dict(tenant_id=tenant, counter_change_id=vehicle + '-ODOMETER-RESET', counter_change_at=stamp(start), counter_change_type='reset', counter_change_evidence='fictional ECU service log reset-2', vehicle_id=vehicle, device_id=_device(tenant, vi, start), signal_definition_id=vehicle + '-odometer', signal_kind='odometer'), start, scenario='ODOMETER-RESET')
                if chosen:
                    w.emit('fuel_task_assignment', dict(tenant_id=tenant, task_assignment_id=trip['trip_id'] + '-ASG', task_id=trip['trip_id'], task_type=trip['task_type'], task_assignment_from=trip['start_at'], task_assignment_to=trip['end_at'], task_start_at=trip['start_at'], task_end_at=trip['end_at'], vehicle_id=vehicle), start, start - timedelta(hours=1))
                minutes = trip['expected_seconds'] // 60
                idle = trip['idle_seconds'] // 60
                pto = trip['pto_seconds'] // 60
                moving = minutes - idle - pto
                weights = [1 + 0.12 * math.sin(i * 0.37) for i in range(moving)]
                wsum = sum(weights)
                fuel_start = physical_fuel
                steps = []
                for minute in range(minutes + 1):
                    when = start + timedelta(minutes=minute)
                    if minute:
                        i = minute - 1
                        if i < idle:
                            distance_delta = 0.0
                            fuel_delta = float(config['idle_l_per_hour']) / 60
                        elif i < idle + pto:
                            distance_delta = 0.0
                            fuel_delta = float(config['pto_l_per_hour']) / 60
                        else:
                            mi = i - idle - pto
                            distance_delta = trip['distance_km'] * weights[mi] / wsum
                            rate = rates['base'] + trip['load_kg'] * rates['load_coefficient_per_kg'] + vi * rates['vehicle_index_coefficient'] + (rates['regional_delivery_increment'] if trip['task_type'] == 'regional_delivery' else 0) + 0.01 * math.sin(j / 9)
                            fuel_delta = distance_delta * rate
                        physical_fuel += fuel_delta
                        counter += fuel_delta
                        odo += distance_delta
                        tank -= fuel_delta
                        if tenant == 'T02' and vi == 2 and (counter >= modulus_l):
                            counter -= modulus_l
                            w.emit('fuel_counter_change', dict(tenant_id=tenant, counter_change_id=f"{trip['trip_id']}-WRAP-{minute}", counter_change_at=stamp(when), counter_change_type='confirmed_rollover', counter_change_evidence='config/simulation.json#fuel_modulus_l', vehicle_id=vehicle, device_id=_device(tenant, vi, when), signal_definition_id=vehicle + '-fuel_total', signal_kind='fuel_total'), when, scenario='CONFIRMED-ROLLOVER')
                        if ti == 1 and vi <= 8:
                            physical.append((vehicle, when - timedelta(minutes=1), when, fuel_delta, distance_delta, trip['task_type'], trip['load_kg'], int(i >= idle and i < idle + pto)))
                    steps.append((when, tank, counter, odo))
                    if not chosen:
                        continue
                    logical = f"{trip['trip_id']}-OBS{minute:04}"
                    scenario = 'FUEL-NORMAL'
                    available = when + timedelta(seconds=15)
                    fuel = counter
                    distance = odo
                    fv = dv = 'valid'
                    unit = 'US_gal' if vi % 2 == 0 else 'L'
                    distance_unit = 'mile' if vi % 2 == 0 else 'km'
                    if tenant == 'T01' and vi == 3 and (j == 19) and (minute in {25, 26}):
                        injections.append(dict(scenario_id='MISSING-PACKET', table='fuel_counter_observation', record_id=logical, expected='retain coverage loss; no invented point'))
                        continue
                    if tenant == 'T02' and vi == 3 and (j == 39) and (minute == 35):
                        fv = 'not_available'
                        fuel = None
                        scenario = 'MISSING-FUEL-ONLY'
                    if tenant == 'T03' and vi == 4 and (j == 29) and (minute == 45):
                        unit = 'unknown'
                        fv = 'unknown'
                        fuel = None
                        scenario = 'UNKNOWN-UNIT'
                    if tenant == 'T01' and vi == 2 and (j == 16) and (minute in {30, 31}):
                        available = when + timedelta(days=4)
                        scenario = 'LATE-PACKET'
                    if tenant == 'T02' and vi == 4 and (j == 20) and (minute == 10):
                        distance = None
                        dv = 'error'
                        scenario = 'DISTANCE-ERROR'
                    row = dict(tenant_id=tenant, counter_observation_id=logical + '-r1', fuel_total_l=rounded(fuel) if fuel is not None else None, odometer_km=rounded(distance) if distance is not None else None, signal_validity='valid' if fv == dv == 'valid' else 'error', fuel_measured_at=stamp(when), fuel_raw_unit=unit, fuel_validity=fv, distance_measured_at=stamp(when), distance_raw_unit=distance_unit, vehicle_id=vehicle, device_id=_device(tenant, vi, when), signal_definition_id=vehicle + '-fuel_total', fuel_total_raw=rounded(counter / GALLON if unit == 'US_gal' else counter), odometer_raw=rounded(odo / MILE if distance_unit == 'mile' else odo), distance_validity=dv, distance_definition_id=vehicle + '-odometer')
                    states = {}
                    if fuel is None:
                        states['fuel_counter_observation.fuel_total_l'] = dict(state='missing' if fv == 'not_available' else 'unknown', reason=scenario)
                    if distance is None:
                        states['fuel_counter_observation.odometer_km'] = dict(state='invalid', reason=scenario)
                    correction = tenant == 'T02' and vi == 3 and (j == 39) and (minute == 50)
                    if correction:
                        row['fuel_total_l'] = rounded(counter + 3)
                        row['fuel_total_raw'] = rounded((counter + 3) / GALLON if unit == 'US_gal' else counter + 3)
                        scenario = 'CORRECTED-COUNTER'
                    w.emit('fuel_counter_observation', row, when, available, scenario, logical, states=states, transport=True)
                    if correction:
                        row2 = dict(row)
                        row2.update(counter_observation_id=logical + '-r2', fuel_total_l=rounded(counter), fuel_total_raw=rounded(counter / GALLON if unit == 'US_gal' else counter))
                        w.emit('fuel_counter_observation', row2, when, when + timedelta(days=3), scenario, logical, version='2', transport=True)
                        injections.append(dict(scenario_id=scenario, table='fuel_counter_observation', record_id=logical, expected='as_of latest revision; original retained'))
                    if scenario != 'FUEL-NORMAL':
                        injections.append(dict(scenario_id=scenario, table='fuel_counter_observation', record_id=logical, expected='apply validity and available-time contract'))
                ledger.extend(steps)
                latent.append(dict(trip_id=trip['trip_id'], tenant_id=tenant, vehicle_id=vehicle, true_fuel_l=rounded(physical_fuel - fuel_start), true_distance_km=trip['distance_km'], closing_volume_l=rounded(tank), selected=chosen))
            ledger.sort(key=lambda x: x[0])
            cursor = 0
            for bi, boundary in enumerate(_boundaries()):
                b = boundary.astimezone(UTC)
                while cursor + 1 < len(ledger) and ledger[cursor + 1][0] <= b:
                    cursor += 1
                _, volume, count, odometer = ledger[cursor]
                unknown = tenant == 'T03' and vi == 9 and (boundary.date().isoformat() == '2025-04-07')
                w.emit('fuel_inventory_measurement', dict(tenant_id=tenant, inventory_measurement_id=f'{vehicle}-INV-{boundary:%Y%m%d}', inventory_measurement_method='unknown' if unknown else 'calibrated_sensor', inventory_uncertainty=2.0, raw_level_percent=rounded(volume / capacity * 100), calibration_curve_ref=None if unknown else 'config/simulation.json#linear_tank_calibration', vehicle_id=vehicle, inventory_tank_scope_id=vehicle + '-TANK', measured_at=stamp(boundary), quantity_l=None if unknown else rounded(volume), raw_quantity=rounded(volume / capacity * 100) if unknown else rounded(volume), raw_quantity_unit='percent' if unknown else 'L', measurement_role='period_boundary'), boundary, boundary + timedelta(hours=1), scenario='UNCALIBRATED-INVENTORY' if unknown else 'WEEKLY-INVENTORY', states={'fuel_inventory_measurement.quantity_l': dict(state='unknown', reason='No calibration evidence')} if unknown else None, evidence='Complete movement ledger Jan1-Jul1; refuel movements reference purchases; unmetered drain explicitly unknown')
                if bi < len(_boundaries()) - 1:
                    for kind in ['transfer_in', 'transfer_out']:
                        w.emit('fuel_movement', dict(tenant_id=tenant, fuel_movement_id=f'{vehicle}-ZERO-{boundary:%Y%m%d}-{kind}', fuel_movement_at=stamp(boundary), fuel_movement_type=kind, fuel_movement_quantity_l=0.0, fuel_movement_reference=f'ledger-completeness:{vehicle}:{boundary:%Y%m%d}; nonzero rows additive', movement_source_scope='confirmed-zero', movement_destination_scope=vehicle + '-TANK', vehicle_id=vehicle), boundary, evidence='Complete ledger confirmation; explicit nonzero entries supplement this zero baseline')
                if profile == 'full':
                    logical = f'{vehicle}-BND-{boundary:%Y%m%d}'
                    w.emit('fuel_counter_observation', dict(tenant_id=tenant, counter_observation_id=logical + '-r1', fuel_total_l=rounded(count), odometer_km=rounded(odometer), signal_validity='valid', fuel_measured_at=stamp(boundary), fuel_raw_unit='US_gal' if vi % 2 == 0 else 'L', fuel_validity='valid', distance_measured_at=stamp(boundary), distance_raw_unit='mile' if vi % 2 == 0 else 'km', vehicle_id=vehicle, device_id=_device(tenant, vi, boundary), signal_definition_id=vehicle + '-fuel_total', fuel_total_raw=rounded(count / GALLON if vi % 2 == 0 else count), odometer_raw=rounded(odometer / MILE if vi % 2 == 0 else odometer), distance_validity='valid', distance_definition_id=vehicle + '-odometer'), boundary, boundary + timedelta(seconds=15), scenario='STATIONARY-WEEK-BOUNDARY', source_id=logical, transport=True)
    for (tenant, year, month, category), c in sorted(control.items()):
        a = datetime(year, month, 1, tzinfo=LA)
        b = datetime(year + int(month == 12), month % 12 + 1, 1, tzinfo=LA)
        statement = f'{tenant}-STMT-{a:%Y%m}'
        w.emit('fuel_statement_control', dict(tenant_id=tenant, statement_control_id=f'{statement}-{category}', statement_period_start=stamp(a), statement_period_end=stamp(b), statement_control_amount=round(c['amount'], 2), statement_control_quantity=rounded(c['quantity']), statement_id=statement, category_code=category, currency='USD', fuel_type='diesel' if category == 'fuel' else 'nonfuel', quantity_unit='L'), b, b + timedelta(days=7), scenario='INDEPENDENT-STATEMENT-CONTROL', evidence='Source accounting totals maintained before source serialization; compare selected final transaction versions')
    statuses = [('accepted', 'confirmed'), ('partly_accepted', 'open'), ('rejected', 'negated'), ('not_reviewed', 'not_reported'), ('accepted', 'disputed'), ('accepted', 'lost_followup'), ('accepted', 'not_mature'), ('accepted', 'confirmed')]
    for i, (adoption, outcome) in enumerate(statuses, 1):
        tenant = 'T01'
        vehicle = f'T01-V{i:02}'
        late = i == 7
        report_week = datetime(2025, 6, 23, tzinfo=LA) if late else datetime(2025, 3, 3, tzinfo=LA)
        action = datetime(2025, 7, 3, tzinfo=LA) if late else datetime(2025, 3, 19, tzinfo=LA)
        base_start = action - timedelta(days=16)
        base_end = action - timedelta(days=2)
        follow_start = action + timedelta(days=1)
        planned = follow_start + timedelta(days=14)
        observed_end = datetime(2025, 7, 10, tzinfo=LA) if late else planned
        review_id = f'{vehicle}-REVIEW-{i:02}'
        rid = output_id(tenant, report_week)
        w.emit('fuel_output_review', dict(tenant_id=tenant, review_case_id=review_id, output_received_at=None if adoption == 'not_reviewed' else stamp(action - timedelta(days=1)), adoption_status=adoption, review_reason=['idle-operation-review', 'price-difference-investigation', 'necessary-PTO-explains-usage', 'no-response', 'task-mix-changed', 'contact-lost', 'followup-window-open', 'counter-quality-repaired'][i - 1], review_outcome=outcome, vehicle_id=vehicle, project_id='DA-E01', output_id=rid, evidence_origin='synthetic_scenario'), action - timedelta(days=1), scenario='SYNTHETIC-REVIEW')
        intervals = [x for x in physical if x[0] == vehicle and x[1] >= follow_start.astimezone(UTC) and (x[2] <= observed_end.astimezone(UTC))]
        missing = outcome in {'not_reported', 'lost_followup', 'not_mature'}
        fuel = None if missing else rounded(sum((x[3] for x in intervals)))
        distance = None if missing else rounded(sum((x[4] for x in intervals)))
        total_distance = sum((x[4] for x in intervals))
        total_duration = len(intervals) * 60
        mix = []
        for task in ['linehaul', 'regional_delivery']:
            subset = [x for x in intervals if x[5] == task]
            if subset:
                mix.append(dict(task_type=task, distance_share=round(sum((x[4] for x in subset)) / total_distance, 6) if total_distance else 0.0, duration_share=round(len(subset) * 60 / total_duration, 6), payload_band='mixed' if i == 5 else 'scenario_matched', pto_share=round(sum((x[7] for x in subset)) / len(subset), 6)))
        w.emit('fuel_action_followup', dict(tenant_id=tenant, action_followup_id=f'{vehicle}-FOLLOWUP-{i:02}', action_id=f'{vehicle}-ACTION-{i:02}', action_type='no_action' if adoption in {'rejected', 'not_reviewed'} else 'operations_review', action_time=None if adoption in {'rejected', 'not_reviewed'} else stamp(action), active_review_seconds=0 if adoption == 'not_reviewed' else 900 + i * 60, baseline_review_seconds=1800, baseline_window_start=stamp(base_start), baseline_window_end=stamp(base_end), followup_start=stamp(follow_start), outcome_observation_end=stamp(observed_end), observed_fuel_l=fuel, action_evidence=f'validation/expected/review_cases.json#{review_id}; values from same physical minute ledger', planned_followup_end=stamp(planned), followup_distance_km=distance, followup_task_mix=mix, investigation_seconds=0 if adoption == 'not_reviewed' else 780 + i * 60, vehicle_id=vehicle, project_id='DA-E01', output_id=rid, evidence_origin='synthetic_scenario', review_case_id=review_id), action, observed_end, scenario='SYNTHETIC-FOLLOWUP', states={f'fuel_action_followup.{k}': dict(state='not_mature' if late else 'missing', reason=outcome) for k in ['observed_fuel_l', 'followup_distance_km'] if missing})
    fixtures = [('HAND-001', 'paired_mpg', dict(start_fuel_l=100.0, end_fuel_l=120.0, start_km=1000.0, end_km=1100.0), 11.7607291667, 'mile/US_gal', None, '100km/1.609344 divided by 20L/3.785411784'), ('HAND-002', 'fuel_balance_l', dict(opening_l=200, closing_l=180, refuel_l=100, transfer_in_l=20, removed_l=10), 130.0, 'L', None, '200+100+20-10-180=130'), ('HAND-003', 'refund_quantity_l', dict(refund_usd=-6.0, quantity_l=0.0), 0.0, 'L', None, 'A price refund has no physical volume'), ('HAND-004', 'unknown_movement_balance', dict(unmetered_drain=True), None, 'L', 'unknown', 'Unknown movement is not zero'), ('HAND-005', 'price_effect_usd', dict(p0=1.0, p1=1.1, q0=100.0, q1=120.0), 10.0, 'USD', None, '(1.1-1.0)*100=10'), ('HAND-006', 'quantity_effect_usd', dict(p0=1.0, p1=1.1, q0=100.0, q1=120.0), 22.0, 'USD', None, '1.1*(120-100)=22; price+quantity=132-100'), ('HAND-007', 'dst_day_seconds', dict(zone='America/Los_Angeles', date='2025-03-09'), 82800.0, 'seconds', None, 'Spring-forward local day has 23 hours'), ('HAND-008', 'counter_reset', dict(before_l=1200.0, after_l=50.0), None, 'L', 'exclude_reset_boundary', 'Discontinuity needs segment evidence')]
    cases = []
    for sid, metric, inputs, value, unit, state, reason in fixtures:
        answer = dict(numeric_value=value, unit=unit, state_value=state, tolerance=1e-06, evidence_ref=f'validation/expected/hand_cases.json#{sid}')
        cases.append(dict(scenario_id=sid, reference_metric=metric, input=inputs, expected=answer, reason=reason))
        w.emit('fuel_reference_case', dict(tenant_id='T01', reference_case_id=sid, reference_metric=metric, expected_value=answer, reference_reviewer_role='independent_arithmetic_fixture', reference_reviewed_at=created, reference_evidence_ref=answer['evidence_ref'], reference_review_status='passed', scenario_id=sid), parse(created), scenario=sid)
    (expected / 'hand_cases.json').write_text(json.dumps(cases, indent=2) + '\n')
    with (expected / 'physical_trip_ledger.jsonl').open('w') as h:
        for row in latent:
            _line(h, row)
    (expected / 'injections.json').write_text(json.dumps(injections, indent=2) + '\n')
    (expected / 'review_cases.json').write_text(json.dumps(dict(scope='Synthetic process exercise, not real adoption or company effects', cases=[dict(review_case_id=f'T01-V{i:02}-REVIEW-{i:02}', adoption_status=a, review_outcome=o) for i, (a, o) in enumerate(statuses, 1)]), indent=2) + '\n')
    w.close()
    (expected / 'malformed_transport.jsonl').write_text('{not-valid-json}\n' + json.dumps(dict(event_id='missing-envelope-fields', payload={})) + '\n')
    source_paths = [root / 'data/raw/events.jsonl']
    source_paths += [root / 'data/raw/tables' / (name + '.jsonl') for name in w.files]
    source_paths += [op / name for name in ('trip_plan.jsonl', 'trips.jsonl', 'drivers.jsonl', 'facilities.json', 'routes.json')]
    manifest = dict(generator_version=VERSION, seed=seed, profile=profile, created_at=created, origin_type='synthetic', world=dict(tenants=3, vehicles=30, devices=36, drivers=45, trips=1800, facilities=12, routes=12), selected_trip_count=len(selected), table_row_counts=dict(w.counts), transport_attempts=w.attempts, output_id_convention='{tenant_id}-FUEL-{Monday_YYYYMMDD}-{initial|revised|retrospective}', smoke_semantics='100 stable trips emit observations; full accounting and inventory closure preserved; trip_plan retains all1800', provenance_retrieved_at_rule='Frozen original dataset creation timestamp; actual replay separately logged', sources=[dict(path=str(p.relative_to(root)), bytes=p.stat().st_size, sha256=file_digest(p)) for p in sorted(source_paths)])
    (root / 'data/generation_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest

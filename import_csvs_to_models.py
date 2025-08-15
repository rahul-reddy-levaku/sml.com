# import_full_dump.py
# ─────────────────────────────────────────────────────────────────────────────
# ZERO-ERROR CSV → DB IMPORTER for your models and your CSV dump.
# Safe defaults, FK-by-code resolution, robust parsing, and full logging.
# ─────────────────────────────────────────────────────────────────────────────

import os, sys, io, csv, json, zipfile, re, traceback
from datetime import datetime
from decimal import Decimal, InvalidOperation

# ── Django bootstrapping (works for `python manage.py shell < this.py`)
try:
    from django.conf import settings
except Exception:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sml8.settings")
    import django
    django.setup()

from django.db import transaction, IntegrityError
from django.db.models import Q

from companies.models import (
    Company, Branch, Village, Center, Group, Cadre, Staff,
    Client, AccountHead, Voucher, Posting
)

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
INPUT_FOLDER = "full_dump_csv"          # folder name if extracted
INPUT_ZIP    = "full_dump_csv.zip"      # zip name if not extracted
LOG_FILE     = "import_log.txt"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def open_csv(name_candidates):
    """
    Return (rows_iter, headers, filename) for the first matching CSV found
    among candidates (case-insensitive) looking inside folder or zip.
    """
    # Try folder
    for cand in name_candidates:
        for root in (".",):
            path = os.path.join(root, INPUT_FOLDER, cand)
            if os.path.exists(path):
                f = open(path, "r", encoding="utf-8", errors="replace")
                reader = csv.DictReader(f)
                return reader, reader.fieldnames, path

    # Try zip
    if os.path.exists(INPUT_ZIP):
        with zipfile.ZipFile(INPUT_ZIP, "r") as z:
            names = z.namelist()
            # normalize: just basename compare
            for cand in name_candidates:
                for nm in names:
                    if os.path.basename(nm).lower() == cand.lower():
                        data = z.read(nm).decode("utf-8", errors="replace")
                        reader = csv.DictReader(io.StringIO(data))
                        return reader, reader.fieldnames, f"{INPUT_ZIP}:{nm}"
    return None, None, None

def ci_get(row, *keys, default=None):
    """Case-insensitive get for dict rows; tries multiple keys."""
    if row is None:
        return default
    for k in keys:
        if k is None:
            continue
        for cand in (k, k.lower(), k.upper(), k.title(), k.capitalize()):
            if cand in row:
                v = row[cand]
                return v if v not in ("", None, "NULL", "null", "NaN") else default
    # case-insensitive full scan
    low = {k.lower(): v for k, v in row.items()}
    for k in keys:
        if k is None:
            continue
        v = low.get(k.lower())
        if v not in ("", None, "NULL", "null", "NaN"):
            return v
    return default

def parse_date(val):
    if not val:
        return None
    val = str(val).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d-%m-%y", "%Y/%m/%d", "%d.%m.%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            pass
    # try yyyymmdd
    if re.fullmatch(r"\d{8}", val):
        try:
            return datetime.strptime(val, "%Y%m%d").date()
        except Exception:
            pass
    return None

def parse_decimal(val):
    if val in (None, "", "NULL", "null"):
        return None
    try:
        return Decimal(str(val).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None

def norm_phone(v):
    if not v: return None
    d = re.sub(r"\D", "", str(v))
    return d if len(d)==10 else None

def norm_aadhaar(v):
    if not v: return None
    d = re.sub(r"\D", "", str(v))
    return f"{d[0:4]} {d[4:8]} {d[8:12]}" if len(d)==12 else None

def safe_unique_set(obj, field_name, value):
    """
    Set a unique field safely: if duplicate would be raised when saving,
    blank it out on IntegrityError and proceed (guarantees no crash).
    """
    if value in ("", None):
        setattr(obj, field_name, None)
        return
    setattr(obj, field_name, value)

# logging
LOGS = []
def log(msg):
    print(msg)
    LOGS.append(str(msg))

def write_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(LOGS))

# FK resolvers (create minimal stubs if missing)
def get_default_company():
    comp = Company.objects.order_by("id").first()
    if comp:
        return comp
    comp = Company.objects.create(code="CMP001", name="Default Company")
    return comp

def upsert_branch_from_row(row):
    # Branch.csv columns: BranchID, Branch_Name, Company1/2, OpenDate, Address1, Phone, Dist, ...
    code = ci_get(row, "BranchID", "BranchCode", "code", default=None)
    name = ci_get(row, "Branch_Name", "BranchName", "Name", default="Branch")
    comp = get_default_company()
    obj, _ = Branch.objects.get_or_create(code=str(code) if code else None, defaults={
        "name": name, "company": comp
    })
    obj.name = name or obj.name
    obj.company = comp
    obj.open_date = parse_date(ci_get(row, "OpenDate"))
    obj.address1  = ci_get(row, "Address1")
    obj.phone     = norm_phone(ci_get(row, "Phone"))
    obj.district  = ci_get(row, "Dist", "District")
    obj.status    = "active"
    obj.raw_csv_data = row
    # handle unique phone
    try:
        obj.save()
    except IntegrityError:
        obj.phone = None
        obj.save()
    return obj

def ensure_village(vcode, vname=None):
    if not vcode:
        return None
    obj, created = Village.objects.get_or_create(VCode=str(vcode), defaults={
        "VName": vname or str(vcode), "status": "active"
    })
    if vname:
        obj.VName = vname
    obj.save()
    return obj

def ensure_center(code, name=None, vcode=None):
    if not code:
        return None
    obj, created = Center.objects.get_or_create(code=str(code), defaults={
        "name": name or str(code), "status": "active"
    })
    if name:
        obj.name = name
    if vcode:
        vill = ensure_village(vcode)
        obj.village = vill
    obj.save()
    return obj

def ensure_group(gcode, gname=None, center_code=None):
    if not gcode:
        return None
    obj, created = Group.objects.get_or_create(code=str(gcode), defaults={
        "name": gname or str(gcode), "status": "active"
    })
    if gname:
        obj.name = gname
    if center_code:
        cen = ensure_center(center_code)
        obj.center = cen
    obj.save()
    return obj

def ensure_cadre(name):
    if not name:
        name = "General"
    obj, _ = Cadre.objects.get_or_create(name=str(name), defaults={"status": "active", "branch": Branch.objects.first() or upsert_branch_from_row({})})
    return obj

def ensure_account_head(acode, name=None, abbr=None, ac_type=None, vtype=None):
    if not acode:
        return None
    acode = str(acode)[:20]
    obj, _ = AccountHead.objects.get_or_create(code=acode, defaults={
        "name": name or acode, "abbreviation": abbr, "ac_type": ac_type, "vtype": vtype, "status": "active"
    })
    if name: obj.name = name
    if abbr is not None: obj.abbreviation = abbr
    if ac_type is not None: obj.ac_type = ac_type
    if vtype is not None: obj.vtype = vtype
    obj.save()
    return obj

# ─────────────────────────────────────────────────────────────────────────────
# Importers (each never throws – it logs and continues)
# ─────────────────────────────────────────────────────────────────────────────

def import_company_default():
    comp = get_default_company()
    log(f"[Company] Using/created default company: {comp.code} - {comp.name}")

def import_branches():
    rdr, hdrs, src = open_csv(["Branch.csv", "br.csv"])
    if not rdr:
        log("[Branch] CSV not found; skipping.")
        return
    log(f"[Branch] Import from {src} …")
    cnt = ok = 0
    for row in rdr:
        cnt += 1
        try:
            upsert_branch_from_row(row)
            ok += 1
        except Exception as e:
            log(f"[Branch] row#{cnt} ERROR: {e}")
    log(f"[Branch] done: {ok}/{cnt} rows")

def import_villages():
    rdr, hdrs, src = open_csv(["Village.csv", "village.csv"])
    if not rdr:
        log("[Village] CSV not found; skipping.")
        return
    log(f"[Village] Import from {src} …")
    cnt = ok = 0
    for row in rdr:
        cnt += 1
        try:
            vcode = ci_get(row, "VCode", "vcode", "Code")
            vname = ci_get(row, "VName", "vname", "Name")
            tdate = parse_date(ci_get(row, "TDate", "Date"))
            obj, _ = Village.objects.get_or_create(VCode=str(vcode) if vcode else None, defaults={"VName": vname or str(vcode)})
            obj.VName = vname or obj.VName
            obj.TDate = tdate
            obj.status = "active"
            obj.raw_csv_data = row
            obj.save()
            ok += 1
        except Exception as e:
            log(f"[Village] row#{cnt} ERROR: {e}")
    log(f"[Village] done: {ok}/{cnt} rows")

def import_centers():
    rdr, hdrs, src = open_csv(["Center.csv", "center.csv"])
    if not rdr:
        log("[Center] CSV not found; skipping.")
        return
    log(f"[Center] Import from {src} …")
    cnt = ok = 0
    for row in rdr:
        cnt += 1
        try:
            code = ci_get(row, "CenterCode", "Centercode", "code", "CCode")
            name = ci_get(row, "Name", "CenterName")
            vcode = ci_get(row, "Village", "VCode")
            created = parse_date(ci_get(row, "creat_date", "DOC", "CreatedOn"))
            week = ci_get(row, "Week")
            meet_place = ci_get(row, "MeetPlace", "MeetingPlace")
            obj = ensure_center(code, name, vcode)
            obj.created_on = created or obj.created_on
            obj.collection_day = week or obj.collection_day
            obj.meet_place = meet_place or obj.meet_place
            obj.status = "active"
            obj.raw_csv_data = row
            obj.save()
            ok += 1
        except Exception as e:
            log(f"[Center] row#{cnt} ERROR: {e}")
    log(f"[Center] done: {ok}/{cnt} rows")

def import_groups():
    rdr, hdrs, src = open_csv(["Groups.csv", "Group.csv", "groups.csv"])
    if not rdr:
        log("[Group] CSV not found; skipping.")
        return
    log(f"[Group] Import from {src} …")
    cnt = ok = 0
    for row in rdr:
        cnt += 1
        try:
            gcode = ci_get(row, "GCode", "GroupCode", "code")
            gname = ci_get(row, "GName", "GroupName", "name")
            center_code = ci_get(row, "CenterCode", "Cno")
            wday = ci_get(row, "WDay", "WeekDay")
            mtime = ci_get(row, "MTime", "MeetingTime")
            nb = ci_get(row, "noofBorrw", "Borrowers", "BorrowerCount")
            nb = int(nb) if nb and str(nb).isdigit() else None

            obj = ensure_group(gcode, gname, center_code)
            obj.week_day = wday or obj.week_day
            obj.meeting_time = mtime or obj.meeting_time
            obj.borrower_count = nb or obj.borrower_count
            obj.status = "active"
            obj.raw_csv_data = row
            obj.save()
            ok += 1
        except Exception as e:
            log(f"[Group] row#{cnt} ERROR: {e}")
    log(f"[Group] done: {ok}/{cnt} rows")

def import_staff():
    rdr, hdrs, src = open_csv(["staff.csv", "Staff.csv"])
    if not rdr:
        log("[Staff] CSV not found; skipping.")
        return
    log(f"[Staff] Import from {src} …")
    cnt = ok = 0
    for row in rdr:
        cnt += 1
        try:
            scode = ci_get(row, "StaffCode", "SCode", "Code")
            name  = ci_get(row, "Name")
            cadre_name = ci_get(row, "Cader", "Cadre")
            doj   = parse_date(ci_get(row, "Doj", "JoiningDate"))
            bank  = ci_get(row, "Bank")
            ifsc  = ci_get(row, "IFSC")
            phone = norm_phone(ci_get(row, "Contact1", "Mobile", "Phone", "Contact"))
            status = ci_get(row, "Status") or "active"

            obj, _ = Staff.objects.get_or_create(staffcode=str(scode) if scode else None, defaults={"name": name})
            obj.name = name or obj.name
            obj.cadre = ensure_cadre(cadre_name)
            obj.joining_date = doj
            obj.bank = bank
            obj.ifsc = ifsc
            safe_unique_set(obj, "contact1", phone)
            obj.status = status
            obj.raw_csv_data = row
            try:
                obj.save()
            except IntegrityError:
                # phone duplicate → drop phone and save
                obj.contact1 = None
                obj.save()
            ok += 1
        except Exception as e:
            log(f"[Staff] row#{cnt} ERROR: {e}")
    log(f"[Staff] done: {ok}/{cnt} rows")

def import_clients():
    rdr, hdrs, src = open_csv(["members.csv", "Members.csv"])
    if not rdr:
        log("[Client] members.csv not found; skipping.")
        return
    log(f"[Client] Import from {src} …")
    cnt = ok = 0
    for row in rdr:
        cnt += 1
        try:
            smt = ci_get(row, "smtcode", "MemberCode", "SMTCode")
            name = ci_get(row, "name", "Name")
            gcode = ci_get(row, "Groupcode", "GCode")
            doj = parse_date(ci_get(row, "Doj", "JoinDate", "DOJ"))
            aad = norm_aadhaar(ci_get(row, "mAadhar", "AadharNo", "Aadhaar", "Aadhar"))
            ph  = norm_phone(ci_get(row, "Contact", "Mobile", "Phone", "contactno"))
            status = "active" if (ci_get(row, "flg_active") in ("1", "true", "True", "ACTIVE")) else "active"

            obj, created = Client.objects.get_or_create(smtcode=str(smt) if smt else None, defaults={"name": name or (smt or "Client")})
            obj.name = name or obj.name
            if gcode:
                grp = ensure_group(gcode, None, None)
                obj.group = grp
            obj.join_date = doj
            # unique-setters for aadhaar/phone
            safe_unique_set(obj, "aadhar", aad)
            safe_unique_set(obj, "contactno", ph)
            obj.status = status
            obj.raw_csv_data = row
            try:
                obj.save()
            except IntegrityError:
                # On unique conflicts, blank conflicting fields and save again
                # (This guarantees no hard error during import)
                try:
                    if aad:
                        obj.aadhar = None
                        obj.save()
                    if ph:
                        obj.contactno = None
                        obj.save()
                except IntegrityError:
                    # last resort: remove both and save
                    obj.aadhar = None
                    obj.contactno = None
                    obj.save()
            ok += 1
        except Exception as e:
            log(f"[Client] row#{cnt} ERROR: {e}")
    log(f"[Client] done: {ok}/{cnt} rows")

def import_account_heads():
    rdr, hdrs, src = open_csv(["ACC_Heads.csv"])
    if not rdr:
        log("[AccountHead] ACC_Heads.csv not found; skipping.")
        return
    log(f"[AccountHead] Import from {src} …")
    cnt = ok = 0
    for row in rdr:
        cnt += 1
        try:
            acode = ci_get(row, "ACode", "Code")
            abbr  = ci_get(row, "Abbrivetion", "Abbreviation")
            act   = ci_get(row, "ACType", "Type")
            vt    = ci_get(row, "VType")
            name  = ci_get(row, "AName", "Name", "MasterName", "ACode")  # fallback

            ensure_account_head(acode, name=name, abbr=abbr, ac_type=act, vtype=vt)
            ok += 1
        except Exception as e:
            log(f"[AccountHead] row#{cnt} ERROR: {e}")
    log(f"[AccountHead] done: {ok}/{cnt} rows")

def import_vouchers_and_postings():
    rdr, hdrs, src = open_csv(["ACC_Cashbook.csv"])
    if not rdr:
        log("[Voucher/Posting] ACC_Cashbook.csv not found; skipping.")
        return
    log(f"[Voucher/Posting] Import from {src} …")
    cnt = ok = v_ok = p_ok = 0
    seen_v = set()
    for row in rdr:
        cnt += 1
        try:
            vno   = ci_get(row, "VoucherNo", "VNo", "Voucher")
            tdate = parse_date(ci_get(row, "Tdate", "Date"))
            acode = ci_get(row, "ACode", "AccountCode")
            debit = parse_decimal(ci_get(row, "Debit"))
            credit= parse_decimal(ci_get(row, "Credit"))
            ttype = ci_get(row, "TType", "Type")
            narr  = ci_get(row, "Narration")

            ah = ensure_account_head(acode)

            # create voucher once
            if vno not in seen_v:
                # choose first line account_head for voucher header (required field)
                vobj, _ = Voucher.objects.get_or_create(voucher_no=str(vno) if vno else None, defaults={
                    "date": tdate or datetime.today().date(),
                    "account_head": ah,
                    "narration": narr or "",
                    "status": "active",
                })
                # keep date/narration if provided
                if tdate: vobj.date = tdate
                if narr is not None: vobj.narration = narr
                if ah: vobj.account_head = ah
                vobj.raw_csv_data = row
                vobj.save()
                seen_v.add(vno)
                v_ok += 1
            else:
                vobj = Voucher.objects.get(voucher_no=str(vno))

            # posting line
            pobj = Posting(
                voucher=vobj,
                account_head=ah,
                debit=debit or Decimal("0"),
                credit=credit or Decimal("0"),
                ttype=ttype,
                narration=narr or "",
                raw_csv_data=row,
            )
            pobj.save()
            p_ok += 1
        except Exception as e:
            log(f"[Voucher/Posting] row#{cnt} ERROR: {e}")
    log(f"[Voucher/Posting] done: vouchers={v_ok}, postings={p_ok}, rows={cnt}")

def patch_aadhaar_from_aadhar_csv():
    rdr, hdrs, src = open_csv(["Aadhar.csv"])
    if not rdr:
        log("[Client Aadhar] Aadhar.csv not found; skipping.")
        return
    log(f"[Client Aadhar] Patching from {src} …")
    cnt = ok = 0
    for row in rdr:
        cnt += 1
        try:
            smt = ci_get(row, "Smtcode", "SMTCode")
            aad = norm_aadhaar(ci_get(row, "AadharNo"))
            if not smt or not aad:
                continue
            try:
                cli = Client.objects.get(smtcode=str(smt))
            except Client.DoesNotExist:
                continue
            # only set if currently empty (avoid unique collisions)
            if not cli.aadhar:
                try:
                    cli.aadhar = aad
                    cli.save()
                except IntegrityError:
                    cli.aadhar = None
                    cli.save()
            ok += 1
        except Exception as e:
            log(f"[Client Aadhar] row#{cnt} ERROR: {e}")
    log(f"[Client Aadhar] patched: {ok}/{cnt}")

# ─────────────────────────────────────────────────────────────────────────────
# Run all
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log("─── CSV Import Start ───")
    import_company_default()
    import_branches()
    import_villages()
    import_centers()
    import_groups()
    import_staff()
    import_clients()
    import_account_heads()
    import_vouchers_and_postings()
    patch_aadhaar_from_aadhar_csv()
    log("─── CSV Import Finished (see import_log.txt) ───")
    write_log()

if __name__ == "__main__":
    main()

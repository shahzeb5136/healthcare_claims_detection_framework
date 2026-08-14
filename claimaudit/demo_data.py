"""
Synthetic demonstration claims.

Fifteen claims, each built to exercise a specific part of the fleet, plus one
deliberately clean claim so the demonstration shows the agents returning
no_finding rather than only showing them finding things. Specificity matters as
much as sensitivity: an audit system that flags everything is not an audit system.

`demo_note` on each claim records what it was built to exercise. It is shown in
the UI as "what to look for" and is NEVER included in anything sent to an agent —
see Claim.to_agent_context(), which does not read it.

Every member is a surrogate key with an age band. No synthetic person has a name,
an Emirates ID, a passport number or a date of birth, because the production
platform would not send those across the model boundary either.
"""

from __future__ import annotations

from .schema import Activity, Claim, Diagnosis


def _totals(activities: list[Activity], patient_share: float) -> tuple[float, float]:
    gross = round(sum(a.gross_amount for a in activities), 2)
    return gross, round(gross - patient_share, 2)


def _mk(
    claim_id: str,
    activities: list[Activity],
    diagnoses: list[Diagnosis],
    patient_share: float,
    **kwargs,
) -> Claim:
    gross, net = _totals(activities, patient_share)
    return Claim(
        claim_id=claim_id,
        gross_amount=gross,
        patient_share=patient_share,
        net_amount=net,
        activities=activities,
        diagnoses=diagnoses,
        **kwargs,
    )


# --------------------------------------------------------------------------

_PLAN = dict(
    plan_code="HC-COMP-GOLD-2026",
    policy_start="2026-01-01",
    policy_end="2026-12-31",
    network_tier="Gold",
    emirate="Abu Dhabi",
    source_channel="direct",
)


def build_demo_claims() -> list[Claim]:
    claims: list[Claim] = []

    # ------------------------------------------------------------------ 101
    claims.append(
        _mk(
            "CLM-2026-000101",
            [
                Activity("ACT-001", "99214", "CPT",
                         "Office visit, established patient, moderate complexity",
                         1, 450.00, 450.00, ["25"], "2026-06-16", 25, "Dr F Al Marzooqi"),
                Activity("ACT-002", "97110", "CPT",
                         "Therapeutic exercise, each 15 minutes",
                         4, 180.00, 720.00, [], "2026-06-16", 60, "S Raghavan, PT"),
                Activity("ACT-003", "97140", "CPT",
                         "Manual therapy techniques, each 15 minutes",
                         2, 160.00, 320.00, [], "2026-06-16", 30, "S Raghavan, PT"),
            ],
            [
                Diagnosis("M23.322", "ICD-10-CM", "principal", 1,
                          "Other meniscus derangements, posterior horn of medial meniscus, left knee"),
                Diagnosis("Z98.890", "ICD-10-CM", "secondary", 2,
                          "Other specified postprocedural states"),
            ],
            patient_share=258.00,
            submission_date="2026-06-18",
            encounter_type="outpatient",
            encounter_start="2026-06-16",
            encounter_end="2026-06-16",
            facility_name="Al Noor Orthopaedic Centre",
            facility_licence_id="DOH-F-0004821",
            facility_type="Clinic",
            clinician_name="Dr Faisal Al Marzooqi",
            clinician_licence_id="DOH-P-0091274",
            clinician_specialty="Orthopaedic Surgery",
            member_sk="MBR-4471902",
            member_age=38,
            member_gender="male",
            policy_number="POL-CORP-88214",
            scheme_inception="2024-01-01",
            prior_auth_status="not_obtained",
            attachments=["Consultation note 16 Jun 2026", "Physiotherapy session log"],
            clinical_notes=(
                "Post-operative review. Arthroscopic partial medial meniscectomy (CPT 29881) was "
                "performed on the RIGHT knee on 14 June 2026 at this facility under claim "
                "CLM-2026-000098. The patient attends today for routine post-operative "
                "physiotherapy. Wound clean and dry, no effusion, range of movement improving as "
                "expected. No new complaint and no change to the management plan.\n"
                "This is the ninth physiotherapy session in the current policy year.\n"
                "Plan: continue the existing physiotherapy programme, review in three weeks."
            ),
            demo_note=(
                "Built for B05 (diagnosis says LEFT knee, the operative record says RIGHT), "
                "B07 (modifier 25 on an E/M with no separately identifiable service documented), "
                "B08 (97110 and 97140 billed inside the 90-day global period of 29881), and "
                "E04 (physiotherapy beyond the sixth session requires pre-authorisation, §6.1(e), "
                "and none was obtained)."
            ),
            **_PLAN,
        )
    )

    # ------------------------------------------------------------------ 102
    claims.append(
        _mk(
            "CLM-2026-000102",
            [
                Activity("ACT-001", "99215", "CPT",
                         "Office visit, established patient, high complexity",
                         1, 600.00, 600.00, [], "2026-04-21", 40, "Dr H Kassem"),
                Activity("ACT-002", "93000", "CPT",
                         "Electrocardiogram, routine, with interpretation",
                         1, 150.00, 150.00, [], "2026-04-21", 10, "Dr H Kassem"),
                Activity("ACT-003", "93306", "CPT",
                         "Transthoracic echocardiography, complete with Doppler",
                         1, 1200.00, 1200.00, [], "2026-04-21", 35, "Dr H Kassem"),
                Activity("ACT-004", "93351", "CPT",
                         "Stress echocardiography, complete",
                         1, 2400.00, 2400.00, [], "2026-04-21", 60, "Dr H Kassem"),
                Activity("ACT-005", "75574", "CPT",
                         "CT coronary angiography with contrast",
                         1, 4800.00, 4800.00, [], "2026-04-21", 45, "Dr N Farouk"),
                Activity("ACT-006", "80061", "CPT", "Lipid panel",
                         1, 220.00, 220.00, [], "2026-04-21", None, "Laboratory"),
                Activity("ACT-007", "84484", "CPT", "Troponin, quantitative",
                         1, 180.00, 180.00, [], "2026-04-21", None, "Laboratory"),
                Activity("ACT-008", "83880", "CPT", "Natriuretic peptide (BNP)",
                         1, 260.00, 260.00, [], "2026-04-21", None, "Laboratory"),
                Activity("ACT-009", "85025", "CPT", "Complete blood count with differential",
                         1, 90.00, 90.00, [], "2026-04-21", None, "Laboratory"),
                Activity("ACT-010", "80053", "CPT", "Comprehensive metabolic panel",
                         1, 140.00, 140.00, [], "2026-04-21", None, "Laboratory"),
            ],
            [
                Diagnosis("R07.9", "ICD-10-CM", "principal", 1, "Chest pain, unspecified"),
                Diagnosis("R00.2", "ICD-10-CM", "secondary", 2, "Palpitations"),
            ],
            patient_share=50.00,
            submission_date="2026-04-23",
            encounter_type="outpatient",
            encounter_start="2026-04-21",
            encounter_end="2026-04-21",
            facility_name="Gulf Heart Institute",
            facility_licence_id="DOH-F-0001133",
            facility_type="Hospital",
            clinician_name="Dr Hana Kassem",
            clinician_licence_id="DOH-P-0044019",
            clinician_specialty="Cardiology",
            member_sk="MBR-2298114",
            member_age=34,
            member_gender="female",
            policy_number="POL-CORP-77410",
            scheme_inception="2023-06-01",
            prior_auth_status="not_obtained",
            attachments=["Cardiology consultation note", "ECG tracing", "Echo report"],
            clinical_notes=(
                "34-year-old, non-smoker, no family history of premature coronary disease, BMI 23. "
                "Two-week history of intermittent left-sided sharp chest discomfort lasting seconds, "
                "reproducible on chest wall palpation, unrelated to exertion. No dyspnoea, syncope "
                "or diaphoresis. Examination unremarkable. Resting ECG normal sinus rhythm, no "
                "ischaemic changes. Troponin within reference range.\n"
                "All investigations listed were ordered and performed on the same day of "
                "attendance. No prior non-invasive testing has been performed and no trial of "
                "conservative management is documented."
            ),
            demo_note=(
                "Built for C03 (a resting echo, a stress echo and a CT coronary angiogram ordered "
                "on the same day for atypical, reproducible chest wall pain in a low-risk patient), "
                "C01 (necessity narrative), B09 (level 5 E/M against the documented work), and "
                "E04 (the claim exceeds the AED 5,000 pre-authorisation threshold, §6.1(i), and CT "
                "requires pre-authorisation in its own right, §6.1(c))."
            ),
            **_PLAN,
        )
    )

    # ------------------------------------------------------------------ 103
    claims.append(
        _mk(
            "CLM-2026-000103",
            [
                Activity("ACT-001", "59400", "CPT",
                         "Routine obstetric care including antepartum care, vaginal delivery and postpartum care",
                         1, 12000.00, 12000.00, [], "2026-02-09", None, "Dr L Georgiou"),
                Activity("ACT-002", "99213", "CPT",
                         "Office visit, established patient, low complexity",
                         1, 300.00, 300.00, [], "2026-02-09", 15, "Dr L Georgiou"),
            ],
            [
                Diagnosis("O80", "ICD-10-CM", "principal", 1,
                          "Encounter for full-term uncomplicated delivery"),
                Diagnosis("Z3490", "ICD-10-CM", "secondary", 2,
                          "Encounter for supervision of normal pregnancy, unspecified"),
                Diagnosis("I10", "ICD-10-CM", "secondary", 3, "Essential (primary) hypertension"),
            ],
            patient_share=50.00,
            submission_date="2026-02-11",
            encounter_type="inpatient",
            encounter_start="2026-02-08",
            encounter_end="2026-02-09",
            length_of_stay_days=1,
            facility_name="Marina Women's Hospital",
            facility_licence_id="DOH-F-0007710",
            facility_type="Hospital",
            clinician_name="Dr Lena Georgiou",
            clinician_licence_id="DOH-P-0066123",
            clinician_specialty="Obstetrics and Gynaecology",
            member_sk="MBR-5510338",
            member_age=47,
            member_gender="male",
            policy_number="POL-CORP-88214",
            scheme_inception="2024-01-01",
            prior_auth_status="obtained",
            prior_auth_number="PA-2026-009871",
            attachments=["Discharge summary"],
            clinical_notes=(
                "Discharge summary attached. Note that the membership record for this member key "
                "records gender as male and age band 45-49. The attached discharge summary refers "
                "to a 29-year-old primigravida. The claim was submitted under this member key."
            ),
            demo_note=(
                "Built for B06 (obstetric delivery codes billed against a male member in the 45-49 "
                "age band), B03 (diagnosis/procedure coherence), and T0-09 (the diagnosis 'Z3490' "
                "is not a well-formed ICD-10 code — the decimal point is missing). The mismatch "
                "between the membership record and the attached document is the kind of signal "
                "Squad F would pursue as possible card misuse; Squad F is out of scope here."
            ),
            **_PLAN,
        )
    )

    # ------------------------------------------------------------------ 104
    claims.append(
        _mk(
            "CLM-2026-000104",
            [
                Activity("ACT-001", "30520", "CPT",
                         "Septoplasty or submucous resection, with or without cartilage scoring",
                         1, 14000.00, 14000.00, [], "2026-05-12", 75, "Dr T Al Hashimi"),
                Activity("ACT-002", "30400", "CPT",
                         "Rhinoplasty, primary; lateral and alar cartilages and/or elevation of nasal tip",
                         1, 18000.00, 18000.00, [], "2026-05-12", 90, "Dr T Al Hashimi"),
                Activity("ACT-003", "00160", "CPT",
                         "Anaesthesia for procedures on nose and accessory sinuses",
                         1, 2600.00, 2600.00, [], "2026-05-12", 165, "Dr R Mehta"),
            ],
            [
                Diagnosis("J34.2", "ICD-10-CM", "principal", 1, "Deviated nasal septum"),
            ],
            patient_share=0.00,
            submission_date="2026-05-14",
            encounter_type="daycase",
            encounter_start="2026-05-12",
            encounter_end="2026-05-12",
            facility_name="Corniche Day Surgery Centre",
            facility_licence_id="DOH-F-0002264",
            facility_type="Day Surgery Centre",
            clinician_name="Dr Tariq Al Hashimi",
            clinician_licence_id="DOH-P-0032887",
            clinician_specialty="Otorhinolaryngology",
            member_sk="MBR-3390215",
            member_age=29,
            member_gender="female",
            policy_number="POL-IND-40113",
            scheme_inception="2022-09-01",
            prior_auth_status="mismatch",
            prior_auth_number="PA-2026-101884",
            attachments=[
                "Operative note 12 May 2026",
                "Pre-operative photographs (frontal, lateral, base)",
                "Post-operative photographs",
            ],
            clinical_notes=(
                "Pre-operative assessment: the patient attended requesting improvement in the "
                "appearance of the nasal dorsum and tip, which she reports has troubled her since "
                "adolescence. On examination the septum is deviated to the left. Nasal endoscopy "
                "was not performed. Rhinomanometry was not performed. The record does not document "
                "nasal obstruction, impaired airflow, recurrent sinusitis or failure of medical "
                "management.\n"
                "Operative note: septoplasty performed, followed by open rhinoplasty with dorsal "
                "hump reduction, osteotomies and tip refinement. Standardised pre- and "
                "post-operative photographs taken for aesthetic comparison.\n"
                "Pre-authorisation PA-2026-101884 was issued for CPT 30520 only."
            ),
            demo_note=(
                "The core Squad E demonstration. E01 must read §1.3 (cosmetic), §1.10 "
                "(reconstructive requires documented functional impairment) and §8.2 together and "
                "conclude that the rhinoplasty component is excluded while the septoplasty is not — "
                "which is exactly the ambiguous case a rule engine mishandles. Also E04 (§6.3: the "
                "service delivered materially differs from the service authorised) and C01."
            ),
            **_PLAN,
        )
    )

    # ------------------------------------------------------------------ 105
    claims.append(
        _mk(
            "CLM-2026-000105",
            [
                Activity("ACT-001", "D0220", "dental",
                         "Intraoral periapical radiograph, first image",
                         2, 120.00, 240.00, [], "2026-06-20", None, "Dr M Younes"),
                Activity("ACT-002", "D1110", "dental", "Prophylaxis, adult",
                         1, 250.00, 250.00, [], "2026-06-20", None, "Dr M Younes"),
                Activity("ACT-003", "D3330", "dental",
                         "Endodontic therapy, molar tooth (excluding final restoration), tooth 36",
                         1, 2400.00, 2400.00, [], "2026-06-20", None, "Dr M Younes"),
                Activity("ACT-004", "D2740", "dental",
                         "Crown, porcelain/ceramic, tooth 36",
                         1, 3200.00, 3200.00, [], "2026-06-20", None, "Dr M Younes"),
            ],
            [
                Diagnosis("K04.7", "ICD-10-CM", "principal", 1,
                          "Periapical abscess without sinus"),
                Diagnosis("K02.9", "ICD-10-CM", "secondary", 2, "Dental caries, unspecified"),
            ],
            patient_share=1218.00,
            submission_date="2026-06-22",
            encounter_type="outpatient",
            encounter_start="2026-06-20",
            encounter_end="2026-06-20",
            facility_name="Khalidiya Dental Care",
            facility_licence_id="DOH-F-0009902",
            facility_type="Dental Clinic",
            clinician_name="Dr Mona Younes",
            clinician_licence_id="DOH-P-0078551",
            clinician_specialty="Endodontics",
            member_sk="MBR-6621047",
            member_age=52,
            member_gender="female",
            policy_number="POL-CORP-99008",
            scheme_inception="2026-04-01",
            prior_auth_status="not_obtained",
            attachments=["Periapical radiographs", "Treatment plan"],
            clinical_notes=(
                "Member presented with pain in the lower left quadrant. Radiographs confirm "
                "periapical radiolucency at tooth 36 with extensive caries. Root canal therapy "
                "completed and a porcelain crown placed at the same visit. There is no history of "
                "trauma and no accident is recorded. Routine scaling and polishing also performed.\n"
                "The member joined this corporate scheme at its inception on 1 April 2026. No "
                "evidence of previous UAE cover has been supplied."
            ),
            demo_note=(
                "A four-clause Squad E claim. E02 must do the arithmetic: scheme inception "
                "1 Apr 2026 to date of service 20 Jun 2026 is under three months against the "
                "six-month dental waiting period at §7.3. E05 must compare the AED 6,090 claimed "
                "to the AED 3,500 dental sub-limit at §4.2. E01 must find that a crown is excluded "
                "unless it follows an accident (§4.3, §8.14). E04 must find dental over AED 1,000 "
                "requires pre-authorisation (§6.1(f))."
            ),
            **_PLAN,
        )
    )

    # ------------------------------------------------------------------ 106
    claims.append(
        _mk(
            "CLM-2026-000106",
            [
                Activity("ACT-001", "44970", "CPT", "Laparoscopic appendectomy",
                         1, 18000.00, 18000.00, [], "2026-03-02", 55, "Dr K Bouazizi"),
                Activity("ACT-002", "99223", "CPT",
                         "Initial hospital inpatient care, high complexity",
                         1, 900.00, 900.00, [], "2026-03-02", 45, "Dr K Bouazizi"),
                # Deliberate arithmetic break: 8 x 420 = 3,360, not 4,200.
                Activity("ACT-003", "99232", "CPT",
                         "Subsequent hospital inpatient care, moderate complexity",
                         8, 420.00, 4200.00, [], "2026-03-03", None, "Dr K Bouazizi"),
                Activity("ACT-004", "99231", "service",
                         "Room and board, private room, per diem",
                         9, 1200.00, 10800.00, [], "2026-03-02", None, "Ward"),
                Activity("ACT-005", "00840", "CPT",
                         "Anaesthesia for intraperitoneal procedures in lower abdomen",
                         1, 3200.00, 3200.00, [], "2026-03-02", 70, "Dr P Nair"),
            ],
            [
                Diagnosis("K59.00", "ICD-10-CM", "principal", 1, "Constipation, unspecified",
                          present_on_admission=True),
                Diagnosis("K35.80", "ICD-10-CM", "secondary", 2,
                          "Unspecified acute appendicitis", present_on_admission=True),
                Diagnosis("Z98.890", "ICD-10-CM", "secondary", 3,
                          "Other specified postprocedural states"),
            ],
            patient_share=0.00,
            submission_date="2026-03-15",
            encounter_type="inpatient",
            encounter_start="2026-03-02",
            encounter_end="2026-03-11",
            length_of_stay_days=9,
            drg_code="06-070",
            facility_name="Eastern Region General Hospital",
            facility_licence_id="DOH-F-0000487",
            facility_type="Hospital",
            clinician_name="Dr Karim Bouazizi",
            clinician_licence_id="DOH-P-0011290",
            clinician_specialty="General Surgery",
            member_sk="MBR-1180553",
            member_age=23,
            member_gender="male",
            policy_number="POL-CORP-77410",
            scheme_inception="2023-06-01",
            prior_auth_status="obtained",
            prior_auth_number="PA-2026-114552",
            attachments=[
                "Operative note 2 Mar 2026",
                "Discharge summary",
                "Nursing observation chart",
            ],
            clinical_notes=(
                "Admitted through the emergency department with right iliac fossa pain, guarding "
                "and a white cell count of 16.2. Ultrasound consistent with acute appendicitis. "
                "Laparoscopic appendectomy performed the same evening; histology confirmed acute "
                "appendicitis without perforation.\n"
                "Post-operative course: afebrile from day 1, tolerating a full diet from day 2, "
                "mobilising independently from day 2, drain removed day 2, wound clean throughout. "
                "No documented complication, no antibiotic escalation, no imaging after day 1.\n"
                "Discharge recorded on day 9. The nursing notes record 'awaiting family "
                "transport / accommodation arrangements' from day 4 onward."
            ),
            demo_note=(
                "Built for C06 (nine-day stay for an uncomplicated laparoscopic appendectomy, with "
                "the record itself documenting a social rather than clinical reason for the delay), "
                "B04 (constipation sequenced as principal ahead of acute appendicitis — the "
                "sequencing that actually drives the DRG), and T0-01 (line ACT-003 is billed at "
                "AED 4,200 where 8 x AED 420 is AED 3,360). Pre-authorisation was properly "
                "obtained, so E04 should return no_finding — that matters as much as the hits."
            ),
            **_PLAN,
        )
    )

    # ------------------------------------------------------------------ 107
    claims.append(
        _mk(
            "CLM-2026-000107",
            [
                Activity("ACT-001", "99213", "CPT",
                         "Office visit, established patient, low complexity",
                         1, 300.00, 300.00, [], "2026-05-18", 15, "Dr A Suleiman"),
                Activity("ACT-002", "72148", "CPT",
                         "MRI lumbar spine without contrast",
                         1, 3400.00, 3400.00, [], "2026-05-18", 30, "Dr N Farouk"),
                Activity("ACT-003", "72141", "CPT",
                         "MRI cervical spine without contrast",
                         1, 3200.00, 3200.00, [], "2026-05-18", 30, "Dr N Farouk"),
            ],
            [
                Diagnosis("M54.50", "ICD-10-CM", "principal", 1, "Low back pain, unspecified"),
            ],
            patient_share=50.00,
            submission_date="2026-05-20",
            encounter_type="outpatient",
            encounter_start="2026-05-18",
            encounter_end="2026-05-18",
            facility_name="Capital Diagnostic Imaging",
            facility_licence_id="DOH-F-0005512",
            facility_type="Diagnostic Centre",
            clinician_name="Dr Amal Suleiman",
            clinician_licence_id="DOH-P-0055603",
            clinician_specialty="Family Medicine",
            member_sk="MBR-8842001",
            member_age=45,
            member_gender="male",
            policy_number="POL-IND-40113",
            scheme_inception="2022-09-01",
            prior_auth_status="not_obtained",
            attachments=["Referral letter", "MRI lumbar report 18 May 2026"],
            clinical_notes=(
                "Six-week history of mechanical low back pain without radiation. No red flags: no "
                "trauma, no weight loss, no fever, no bladder or bowel disturbance, no saddle "
                "anaesthesia. Neurological examination normal. Straight leg raise negative "
                "bilaterally. No neck pain, no upper limb symptoms and no cervical findings are "
                "recorded anywhere in the note.\n"
                "An MRI of the lumbar spine was performed at this facility on 29 April 2026 and "
                "reported as showing mild degenerative change with no nerve root compression. The "
                "clinical picture is unchanged since that study."
            ),
            demo_note=(
                "Built for C03 (a lumbar MRI repeated nineteen days after a normal study with no "
                "interval change, plus a cervical MRI with no cervical symptoms documented at all) "
                "and E04 (MRI requires pre-authorisation under §6.1(c), and the claim also crosses "
                "the AED 5,000 threshold at §6.1(i); none was obtained)."
            ),
            **_PLAN,
        )
    )

    # ------------------------------------------------------------------ 108
    claims.append(
        _mk(
            "CLM-2026-000108",
            [
                Activity("ACT-001", "99214", "CPT",
                         "Office visit, established patient, moderate complexity",
                         1, 450.00, 450.00, [], "2026-07-01", 25, "Dr S Ibrahim"),
                Activity("ACT-002", "DRG-WARF5", "drug", "Warfarin sodium 5 mg tablet",
                         90, 3.20, 288.00, [], "2026-07-01", None, "Pharmacy"),
                Activity("ACT-003", "DRG-DICL50", "drug", "Diclofenac sodium 50 mg tablet",
                         90, 2.10, 189.00, [], "2026-07-01", None, "Pharmacy"),
                Activity("ACT-004", "DRG-OMEP20", "drug", "Omeprazole 20 mg capsule",
                         30, 1.80, 54.00, [], "2026-07-01", None, "Pharmacy"),
            ],
            [
                Diagnosis("I48.91", "ICD-10-CM", "principal", 1,
                          "Unspecified atrial fibrillation"),
                Diagnosis("M17.11", "ICD-10-CM", "secondary", 2,
                          "Unilateral primary osteoarthritis, right knee"),
            ],
            patient_share=103.10,
            submission_date="2026-07-03",
            encounter_type="outpatient",
            encounter_start="2026-07-01",
            encounter_end="2026-07-01",
            facility_name="Al Bateen Family Medicine Centre",
            facility_licence_id="DOH-F-0003345",
            facility_type="Clinic",
            clinician_name="Dr Salma Ibrahim",
            clinician_licence_id="DOH-P-0029914",
            clinician_specialty="Internal Medicine",
            member_sk="MBR-7730192",
            member_age=71,
            member_gender="male",
            policy_number="POL-CORP-99008",
            scheme_inception="2021-03-01",
            prior_auth_status="not_required",
            attachments=["Consultation note", "INR result 1 Jul 2026"],
            clinical_notes=(
                "Routine seven-day review of anticoagulation. Known permanent atrial fibrillation "
                "on warfarin, target INR 2.0-3.0; INR today 2.8, dose unchanged. The patient also "
                "reports right knee pain from established osteoarthritis and was started on "
                "diclofenac at this visit. Omeprazole added for gastric protection.\n"
                "The encounter is a single review visit. All three prescriptions were issued as a "
                "90-day supply, except omeprazole which was issued for 30 days. Next review is "
                "booked in one week."
            ),
            demo_note=(
                "Built for C05 (warfarin plus a non-selective NSAID — a clinically significant "
                "interaction with a real bleeding risk, and a patient-safety signal that should be "
                "routed to clinical review rather than treated as a billing finding) and C04 "
                "(a 90-day supply dispensed against a one-week review interval)."
            ),
            **_PLAN,
        )
    )

    # ------------------------------------------------------------------ 109
    overseas = dict(_PLAN)
    overseas.update(network_tier="Out of network", emirate="n/a", source_channel="reimbursement")
    claims.append(
        _mk(
            "CLM-2026-000109",
            [
                Activity("ACT-001", "29881", "CPT",
                         "Arthroscopy, knee, surgical; with meniscectomy, medial or lateral",
                         1, 22000.00, 22000.00, ["RT"], "2026-04-06", 65, "Dr S Chaiyaphum"),
                Activity("ACT-002", "01382", "CPT",
                         "Anaesthesia for diagnostic arthroscopic procedures of knee joint",
                         1, 3000.00, 3000.00, [], "2026-04-06", 90, "Dr W Prasert"),
                Activity("ACT-003", "99070", "service",
                         "Facility and theatre fee",
                         1, 6000.00, 6000.00, [], "2026-04-06", None, "Facility"),
            ],
            [
                Diagnosis("M17.11", "ICD-10-CM", "principal", 1,
                          "Unilateral primary osteoarthritis, right knee"),
                Diagnosis("M23.221", "ICD-10-CM", "secondary", 2,
                          "Derangement of posterior horn of medial meniscus, right knee"),
            ],
            patient_share=0.00,
            submission_date="2026-04-28",
            encounter_type="daycase",
            encounter_start="2026-04-06",
            encounter_end="2026-04-06",
            place_of_treatment="Thailand",
            facility_name="Bangkok Wellness Surgical Hospital",
            facility_licence_id="TH-HOSP-22417",
            facility_type="Hospital",
            clinician_name="Dr Somchai Chaiyaphum",
            clinician_licence_id="TH-MD-88120",
            clinician_specialty="Orthopaedic Surgery",
            member_sk="MBR-9014477",
            member_age=56,
            member_gender="female",
            policy_number="POL-IND-40113",
            scheme_inception="2022-09-01",
            prior_auth_status="not_obtained",
            attachments=["Overseas invoice", "Operative note (translated)", "Boarding pass copy"],
            clinical_notes=(
                "The member travelled to Bangkok on 3 April 2026. The surgical admission was "
                "arranged with the facility on 12 March 2026, three weeks before departure, as "
                "part of a package that included accommodation. There is no emergency presentation "
                "recorded: the member attended the facility by appointment and was discharged the "
                "same day.\n"
                "No prior written approval was sought from the insurer. The record documents no "
                "trial of physiotherapy, weight management, analgesia or intra-articular injection "
                "before proceeding to arthroscopy."
            ),
            demo_note=(
                "Built for E06 (§2.1 — elective treatment outside the UAE is not covered at all, "
                "and §2.3 requires prior written approval before departure, which was not sought; "
                "the emergency carve-out at §2.2 does not apply because the record shows a planned "
                "admission) and C07 (arthroscopy for degenerative knee disease with no documented "
                "trial of conservative management)."
            ),
            **overseas,
        )
    )

    # ------------------------------------------------------------------ 110  (CLEAN)
    claims.append(
        _mk(
            "CLM-2026-000110",
            [
                Activity("ACT-001", "99213", "CPT",
                         "Office visit, established patient, low complexity",
                         1, 300.00, 300.00, [], "2026-03-24", 20, "Dr Y Al Rashed"),
                Activity("ACT-002", "71046", "CPT", "Radiologic examination, chest, 2 views",
                         1, 260.00, 260.00, [], "2026-03-24", None, "Radiology"),
                Activity("ACT-003", "DRG-AMOXCLA", "drug",
                         "Amoxicillin/clavulanate 625 mg tablet",
                         21, 2.40, 50.40, [], "2026-03-24", None, "Pharmacy"),
                Activity("ACT-004", "DRG-SALBINH", "drug",
                         "Salbutamol 100 mcg inhaler, 200 doses",
                         1, 28.00, 28.00, [], "2026-03-24", None, "Pharmacy"),
            ],
            [
                Diagnosis("J20.9", "ICD-10-CM", "principal", 1,
                          "Acute bronchitis, unspecified"),
            ],
            patient_share=57.84,
            submission_date="2026-03-25",
            encounter_type="outpatient",
            encounter_start="2026-03-24",
            encounter_end="2026-03-24",
            facility_name="Al Bateen Family Medicine Centre",
            facility_licence_id="DOH-F-0003345",
            facility_type="Clinic",
            clinician_name="Dr Yousef Al Rashed",
            clinician_licence_id="DOH-P-0038827",
            clinician_specialty="Family Medicine",
            member_sk="MBR-4471902",
            member_age=41,
            member_gender="male",
            policy_number="POL-CORP-88214",
            scheme_inception="2024-01-01",
            prior_auth_status="not_required",
            attachments=["Consultation note 24 Mar 2026", "Chest radiograph report"],
            clinical_notes=(
                "Five-day history of productive cough with yellow sputum, subjective fever and "
                "chest tightness. Temperature 37.9 C, respiratory rate 18, oxygen saturation 98% "
                "on air. Coarse crackles at the right base clearing on cough, mild expiratory "
                "wheeze. No tachycardia, no hypotension, no confusion.\n"
                "Chest radiograph reported as bronchial wall thickening with no focal "
                "consolidation and no effusion. Treated with a seven-day course of "
                "amoxicillin/clavulanate and a salbutamol inhaler as required. Safety-netting "
                "advice given and documented. Review arranged if not improving in one week."
            ),
            demo_note=(
                "The control claim. Documentation, coding, quantities, necessity, benefit and "
                "member share are all correct. Every agent should return no_finding or "
                "not_applicable, H03 should recommend approve in full, and the run should cost "
                "nothing in auditor time. Specificity is the point: a fleet that flags this claim "
                "is not usable at a hundred thousand claims a month."
            ),
            **_PLAN,
        )
    )

    # ------------------------------------------------------------------ 111
    claims.append(
        _mk(
            "CLM-2026-000111",
            [
                Activity("ACT-001", "99214", "CPT",
                         "Office visit, established patient, moderate complexity",
                         1, 450.00, 450.00, ["25"], "2026-06-02", 20, "Dr I Dawood"),
                Activity("ACT-002", "17110", "CPT",
                         "Destruction of benign lesions other than skin tags, up to 14 lesions",
                         1, 900.00, 900.00, [], "2026-06-02", 20, "Dr I Dawood"),
                Activity("ACT-003", "17999", "CPT",
                         "Unlisted procedure, skin, mucous membrane and subcutaneous tissue",
                         1, 1600.00, 1600.00, ["59"], "2026-06-02", 15, "Dr I Dawood"),
            ],
            [
                Diagnosis("L82.1", "ICD-10-CM", "principal", 1,
                          "Other seborrheic keratosis"),
                Diagnosis("D22.5", "ICD-10-CM", "secondary", 2,
                          "Melanocytic nevi of trunk"),
            ],
            patient_share=50.00,
            submission_date="2026-06-04",
            encounter_type="outpatient",
            encounter_start="2026-06-02",
            encounter_end="2026-06-02",
            facility_name="Reem Dermatology Clinic",
            facility_licence_id="DOH-F-0008820",
            facility_type="Clinic",
            clinician_name="Dr Imran Dawood",
            clinician_licence_id="DOH-P-0071143",
            clinician_specialty="Dermatology",
            member_sk="MBR-2298114",
            member_age=34,
            member_gender="female",
            policy_number="POL-CORP-77410",
            scheme_inception="2023-06-01",
            prior_auth_status="not_required",
            attachments=["Procedure note 2 Jun 2026"],
            clinical_notes=(
                "Attendance booked specifically for removal of lesions assessed and documented at "
                "the consultation of 19 May 2026. No new complaint was raised, no new history was "
                "taken, and no examination beyond the treatment sites is recorded. The note for "
                "today reads in full: 'Attends as planned for cryotherapy. Lesions treated as per "
                "plan. Advised on aftercare.'\n"
                "Eleven seborrheic keratoses were treated by cryotherapy on the trunk and back. "
                "The line coded 17999 describes cryotherapy to three further seborrheic keratoses "
                "on the left shoulder, performed in the same session."
            ),
            demo_note=(
                "Built for B07 (modifier 25 on an E/M where the note documents no service separate "
                "from the pre- and post-procedure work), B02 (an unlisted code used where 17110 "
                "and 17111 specifically describe the service, and the fourteen-lesion allowance of "
                "17110 already covers all fourteen lesions), and B08 (the 17999 line duplicates "
                "work already inside 17110, and modifier 59 does not make it distinct)."
            ),
            **_PLAN,
        )
    )

    # ------------------------------------------------------------------ 112
    claims.append(
        _mk(
            "CLM-2026-000112",
            [
                Activity("ACT-001", "99214", "CPT",
                         "Office visit, established patient, moderate complexity",
                         1, 450.00, 450.00, [], "2026-07-08", 25, "Dr F Nasser"),
                Activity("ACT-002", "83036", "CPT", "Haemoglobin A1c",
                         1, 180.00, 180.00, [], "2026-07-08", None, "Laboratory"),
                Activity("ACT-003", "82043", "CPT", "Albumin, urine, microalbumin, quantitative",
                         1, 140.00, 140.00, [], "2026-07-08", None, "Laboratory"),
                Activity("ACT-004", "80053", "CPT", "Comprehensive metabolic panel",
                         1, 140.00, 140.00, [], "2026-07-08", None, "Laboratory"),
                Activity("ACT-005", "DRG-METF1000", "drug", "Metformin 1000 mg tablet",
                         60, 1.10, 66.00, [], "2026-07-08", None, "Pharmacy"),
                Activity("ACT-006", "DRG-EMPA25", "drug", "Empagliflozin 25 mg tablet",
                         30, 9.50, 285.00, [], "2026-07-08", None, "Pharmacy"),
            ],
            [
                Diagnosis("E11.22", "ICD-10-CM", "principal", 1,
                          "Type 2 diabetes mellitus with diabetic chronic kidney disease"),
                Diagnosis("N18.32", "ICD-10-CM", "secondary", 2,
                          "Chronic kidney disease, stage 3b"),
                Diagnosis("I10", "ICD-10-CM", "secondary", 3,
                          "Essential (primary) hypertension"),
            ],
            patient_share=85.10,
            submission_date="2026-07-10",
            encounter_type="outpatient",
            encounter_start="2026-07-08",
            encounter_end="2026-07-08",
            facility_name="Zayed Endocrine and Diabetes Centre",
            facility_licence_id="DOH-F-0006678",
            facility_type="Clinic",
            clinician_name="Dr Farida Nasser",
            clinician_licence_id="DOH-P-0083311",
            clinician_specialty="Endocrinology",
            member_sk="MBR-3390215",
            member_age=61,
            member_gender="male",
            policy_number="POL-CORP-99008",
            scheme_inception="2026-05-01",
            prior_auth_status="not_required",
            attachments=["Consultation note", "Laboratory report", "Previous medication list"],
            clinical_notes=(
                "Member enrolled on this corporate scheme at its inception on 1 May 2026. "
                "Routine diabetes review. The medication list supplied by the member records "
                "continuous metformin therapy since 2019 and a diagnosis of type 2 diabetes "
                "mellitus made in 2019 at a clinic in Al Ain. HbA1c today 8.4%. eGFR 41. "
                "Empagliflozin added for renal protection.\n"
                "No certificate of previous UAE health insurance cover has been supplied, and the "
                "employer has not confirmed whether the member transferred from another insurer "
                "without a break in cover."
            ),
            demo_note=(
                "Built for E03 and E02 together. The condition plainly meets both the pre-existing "
                "definition at §1.9 and the chronic definition at §1.2, and §7.5 imposes a "
                "six-month waiting period which has not expired. But §7.6 waives it on continuous "
                "transfer, and that evidence has not been supplied — so the correct answer is to "
                "request information and refer, not to deny. This claim tests whether the agents "
                "reach for the waiver clause rather than stopping at the exclusion."
            ),
            **_PLAN,
        )
    )

    # ------------------------------------------------------------------ 113
    claims.append(
        _mk(
            "CLM-2026-000113",
            [
                Activity("ACT-001", "99213", "CPT",
                         "Office visit, established patient, low complexity",
                         1, 300.00, 300.00, [], "2026-05-05", 15, "Dr G Haddad"),
                Activity("ACT-002", "87880", "CPT",
                         "Infectious agent detection, Streptococcus group A, direct optical",
                         1, 120.00, 120.00, [], "2026-05-05", None, "Laboratory"),
                Activity("ACT-003", "42820", "CPT",
                         "Tonsillectomy and adenoidectomy; younger than age 12",
                         1, 9500.00, 9500.00, [], "2026-05-05", 55, "Dr G Haddad"),
                Activity("ACT-004", "DRG-AMOX500", "drug", "Amoxicillin 500 mg capsule",
                         21, 1.90, 39.90, [], "2026-05-05", None, "Pharmacy"),
            ],
            [
                Diagnosis("J02.9", "ICD-10-CM", "principal", 1,
                          "Acute pharyngitis, unspecified"),
                Diagnosis("J35.01", "ICD-10-CM", "secondary", 2, "Chronic tonsillitis"),
            ],
            patient_share=53.99,
            submission_date="2026-05-07",
            encounter_type="outpatient",
            encounter_start="2026-05-05",
            encounter_end="2026-05-05",
            facility_name="Reem Paediatric and ENT Clinic",
            facility_licence_id="DOH-F-0008820",
            facility_type="Clinic",
            clinician_name="Dr George Haddad",
            clinician_licence_id="DOH-P-0064802",
            clinician_specialty="Paediatrics",
            member_sk="MBR-5510338",
            member_age=4,
            member_gender="female",
            policy_number="POL-CORP-88214",
            scheme_inception="2024-01-01",
            prior_auth_status="not_obtained",
            attachments=["Consultation note 5 May 2026"],
            clinical_notes=(
                "First recorded presentation for sore throat. Two days of fever and odynophagia. "
                "Tonsils enlarged and erythematous with exudate, tender cervical nodes. Rapid "
                "streptococcal antigen positive. Weight 17 kg.\n"
                "There is no documented history of recurrent tonsillitis, no record of previous "
                "episodes, no antibiotic course history and no prior referral. The tonsillectomy "
                "and adenoidectomy was performed at the clinic on the same day as the "
                "consultation. No operative note or anaesthetic record is attached. Amoxicillin "
                "500 mg capsules were dispensed three times daily for seven days."
            ),
            demo_note=(
                "Built for C08 and C07. Amoxicillin 500 mg capsules three times daily is an adult "
                "dose for a 17 kg four-year-old, and a capsule is the wrong formulation for that "
                "age. Tonsillectomy at a first presentation, with no documented recurrent episodes, "
                "does not meet any recognised indication threshold. Also B06 (age band against the "
                "dispensed dose), E04 (surgery under anaesthesia plus the AED 5,000 threshold), "
                "and T0-13 (a surgical line with no operative note attached)."
            ),
            **_PLAN,
        )
    )

    # ------------------------------------------------------------------ 114
    claims.append(
        _mk(
            "CLM-2026-000114",
            [
                Activity("ACT-001", "92015", "CPT", "Determination of refractive state",
                         1, 200.00, 200.00, [], "2026-02-17", None, "Optometrist"),
                Activity("ACT-002", "OPT-LENS-BI", "service",
                         "Prescription lenses, bilateral, high index",
                         1, 950.00, 950.00, [], "2026-02-17", None, "Dispensing"),
                Activity("ACT-003", "OPT-FRAME-D", "service",
                         "Spectacle frames, designer range",
                         1, 900.00, 900.00, [], "2026-02-17", None, "Dispensing"),
                Activity("ACT-004", "OPT-SUN-RX", "service",
                         "Prescription sunglasses, tinted",
                         1, 750.00, 750.00, [], "2026-02-17", None, "Dispensing"),
            ],
            [
                Diagnosis("H52.13", "ICD-10-CM", "principal", 1, "Myopia, bilateral"),
            ],
            patient_share=560.00,
            submission_date="2026-02-19",
            encounter_type="outpatient",
            encounter_start="2026-02-17",
            encounter_end="2026-02-17",
            facility_name="Vision First Optical",
            facility_licence_id="DOH-F-0011204",
            facility_type="Optical Centre",
            clinician_name="Ms Reem Al Suwaidi",
            clinician_licence_id="DOH-P-0099021",
            clinician_specialty="Optometry",
            member_sk="MBR-6621047",
            member_age=52,
            member_gender="female",
            policy_number="POL-CORP-99008",
            scheme_inception="2023-01-01",
            prior_auth_status="not_required",
            attachments=["Refraction record", "Dispensing invoice"],
            clinical_notes=(
                "Routine refraction. Prescription -3.25 DS right, -3.50 DS left, stable against "
                "the previous prescription of February 2025. One pair of high-index single-vision "
                "lenses dispensed with a designer frame. A second, tinted prescription pair was "
                "dispensed at the same visit at the member's request for outdoor use.\n"
                "No pathology identified. No previous optical claim recorded in the current policy "
                "year."
            ),
            demo_note=(
                "Built for E05 and E01 in the same breath. §4.2 sets the optical sub-limit at "
                "AED 1,500 against AED 2,800 claimed; §4.4 caps frames at AED 400 and covers one "
                "pair of lenses per policy year; and §4.4 excludes sunglasses outright. Three "
                "separate clause-level findings that a benefit-code lookup would miss entirely."
            ),
            **_PLAN,
        )
    )

    # ------------------------------------------------------------------ 115
    claims.append(
        _mk(
            "CLM-2026-000115",
            [
                Activity("ACT-001", "97110", "CPT", "Therapeutic exercise, each 15 minutes",
                         4, 190.00, 760.00, [], "2026-07-02", 60, "N Okafor, PT"),
                Activity("ACT-002", "97140", "CPT", "Manual therapy techniques, each 15 minutes",
                         3, 210.00, 630.00, [], "2026-07-02", 45, "N Okafor, PT"),
                Activity("ACT-003", "97035", "CPT", "Ultrasound therapy, each 15 minutes",
                         3, 160.00, 480.00, [], "2026-07-02", 45, "N Okafor, PT"),
                Activity("ACT-004", "97012", "CPT", "Mechanical traction",
                         3, 150.00, 450.00, [], "2026-07-02", 45, "N Okafor, PT"),
                Activity("ACT-005", "97530", "CPT", "Therapeutic activities, each 15 minutes",
                         4, 210.00, 840.00, [], "2026-07-02", 60, "N Okafor, PT"),
                Activity("ACT-006", "97014", "CPT", "Electrical stimulation, unattended",
                         4, 180.00, 720.00, [], "2026-07-02", 60, "N Okafor, PT"),
                Activity("ACT-007", "97124", "CPT", "Massage therapy, each 15 minutes",
                         4, 190.00, 760.00, [], "2026-07-02", 60, "N Okafor, PT"),
            ],
            [
                Diagnosis("M54.50", "ICD-10-CM", "principal", 1, "Low back pain, unspecified"),
                Diagnosis("M54.16", "ICD-10-CM", "secondary", 2, "Radiculopathy, lumbar region"),
            ],
            patient_share=928.00,
            submission_date="2026-07-04",
            encounter_type="outpatient",
            encounter_start="2026-07-02",
            encounter_end="2026-07-02",
            facility_name="Corniche Rehabilitation Centre",
            facility_licence_id="DOH-F-0002264",
            facility_type="Rehabilitation Centre",
            clinician_name="Ms Ngozi Okafor",
            clinician_licence_id="DOH-P-0090442",
            clinician_specialty="Physiotherapy",
            member_sk="MBR-8842001",
            member_age=45,
            member_gender="male",
            policy_number="POL-IND-40113",
            scheme_inception="2022-09-01",
            prior_auth_status="not_obtained",
            attachments=["Physiotherapy assessment", "Session log 2 Jul 2026"],
            clinical_notes=(
                "Twelve-session physiotherapy programme prescribed on 28 June 2026 for mechanical "
                "low back pain as a single block of treatment. Seven modalities were delivered in "
                "one attendance lasting a recorded ninety minutes in total.\n"
                "Three further claims have been submitted by this facility for the same member for "
                "physiotherapy delivered on 5, 9 and 12 July 2026, at AED 4,850, AED 4,760 and "
                "AED 4,690 respectively. Each attendance is billed as a separate claim. The "
                "twelve sessions were prescribed, scheduled and delivered as one course of "
                "treatment.\n"
                "This attendance is session 7 of the current policy year for this member."
            ),
            demo_note=(
                "Built for E04 (§6.6 expressly prohibits dividing one episode of care across "
                "claims or dates to stay below the AED 5,000 threshold at §6.1(i), and §6.1(e) "
                "requires pre-authorisation beyond the sixth session — this is session 7), E05 "
                "(the physiotherapy sub-limit of AED 6,000 and 20 sessions at §4.2), and C03 "
                "(seven passive and active modalities stacked into one ninety-minute attendance). "
                "Note the honest limit: the *cross-claim* pattern is what Squad D05 and Squad F "
                "would prove. Here the agents can only reason from what the record states, which "
                "is why the note says it explicitly."
            ),
            **_PLAN,
        )
    )

    return claims


DEMO_CLAIM_SUMMARY = [
    ("CLM-2026-000101", "Orthopaedic follow-up — global period, laterality, modifier 25"),
    ("CLM-2026-000102", "Cardiology — investigation stacking on low-risk chest pain"),
    ("CLM-2026-000103", "Obstetric codes on a male member — gender edit and code format"),
    ("CLM-2026-000104", "ENT — cosmetic versus reconstructive, authorisation mismatch"),
    ("CLM-2026-000105", "Dental — waiting period, sub-limit, crown exclusion, pre-auth"),
    ("CLM-2026-000106", "Inpatient appendectomy — length of stay, DRG sequencing, arithmetic"),
    ("CLM-2026-000107", "Imaging — repeat MRI and an unindicated second region, no pre-auth"),
    ("CLM-2026-000108", "Pharmacy — warfarin/NSAID interaction, 90-day supply on a 7-day review"),
    ("CLM-2026-000109", "Elective surgery in Thailand — territorial scope"),
    ("CLM-2026-000110", "Acute bronchitis — clean claim, control"),
    ("CLM-2026-000111", "Dermatology — modifier 25, unlisted code, unbundling"),
    ("CLM-2026-000112", "Endocrinology — pre-existing and chronic on a new scheme"),
    ("CLM-2026-000113", "Paediatrics — adult dosing and unindicated tonsillectomy"),
    ("CLM-2026-000114", "Optical — sub-limit, frame cap, sunglasses exclusion"),
    ("CLM-2026-000115", "Physiotherapy — split billing and modality stacking"),
]

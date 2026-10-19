# Data-use and acquisition finding — 2026-10-19

Scope: student research prototype for the Happiest Health Digital Twin Challenge.
Competition participation is intended. Separate commercial deployment, data/model
distribution and a commercial rights grant are **not established intentions**.
This review is an interpretation of identified terms, not legal clearance.

## Sources and findings

- [Official release](https://www.physionet.org/content/cgmacros/1.0.0/): open access,
  available to anyone complying with the specified license. No credential, training
  certificate or separate download application is stated on this release page.
  Login is required to view the corresponding author's contact details, not stated
  as a requirement for the public files.
- [Full applicable license](https://physionet.org/content/cgmacros/view-license/1.0.0/):
  CC BY-NC-SA 4.0. Sections 1(k), 2(a)(1), 3 and 4 establish the purpose-based
  NonCommercial test, reproduction/adaptation rights, attribution/change notices,
  conditional ShareAlike and database rights. Sections 2(b) and 5 do not provide
  blanket privacy, publicity, patent or third-party-rights assurances.
- [Creative Commons explanation](https://creativecommons.org/faq/#does-my-use-violate-the-noncommercial-clause-of-the-licenses):
  actual use and intention matter; organizational type alone does not decide.
  Prize participation is not expressly classified by the dataset license.
- [Organizer's challenge listing](https://unstop.com/hackathons/crp-digital-twin-challenge-2026-happiest-health-1757873/amp):
  calls for a student proof of concept, public GitHub source, license details and
  demonstrations, and permits anonymized/open/synthetic inputs. No challenge-specific
  IP assignment or third-party-license exception was found in the accessible listing.
  This does not prove none exists in registration/submission terms.
- [Happiest Health general terms, section 5](https://www.happiesthealth.com/terms-conditions):
  user submissions carry broad exploitation/sublicensing rights and a warranty
  that the submitter has the needed rights. Applicability to this Unstop challenge
  and to a linked public repository was not established. Do not silently apply
  these website terms as challenge-specific terms. Unstop terms pages attempted
  in this review were unavailable; unrelated simulation-service terms were excluded.

| Activity | Finding for the stated scope |
|---|---|
| Local processing/research training | **Supported by identified terms** for a genuinely noncommercial research purpose; no separate permission letter is intrinsically required. This is an application of the license, not an unconditional training authorization. |
| Competition demonstration | **Unresolved** end-to-end: an educational demonstration is not automatically commercial, but the applicable submission/publicity rights and exact submitted material must be established. Synthetic demonstrations avoid transferring CGMacros material, but do not alone determine the purpose of research processing. |
| Public independent source code | **Supported by identified terms** for the project's own rights under its MIT license. Dataset terms do not automatically convert independent code to NC-SA. Source-derived content needs separate treatment. |
| Dataset/model redistribution | Dataset sharing is **supported** only within the license's noncommercial/attribution and applicable ShareAlike conditions. Whether particular weights contain protected/adapted material is **unresolved**, not automatically covered or prohibited. No redistribution is currently intended or authorized by this review. |
| Rights granted to organizer | **Unresolved**: own-code rights can be granted; unrestricted sublicensing/commercial rights over protected dataset-derived material are **outside the stated dataset grant**. The license is non-sublicensable; recipients instead receive their own offer from the licensor. |
| Future commercial deployment | **Outside the stated grant** to the extent it exercises licensed dataset rights commercially. No such deployment is currently assumed. Independent code and unprotected facts are not automatically subject to dataset copyright restrictions. |

Repository records reviewed: `LICENSE`, `docs/licensing_and_permissions_tracker.md`,
`docs/stage1/{licensing_and_permissions.md,source_register.csv,leakage_audit.md}`,
and `reports/stage1/provenance_manifest.json`. Their blanket competition block
should not be read as proof of prohibition. The current primary release identifies
CC BY-NC-SA; it does **not** substantiate the additional ODC-BY label asserted in
the tracker/LICENSE. No alternate-deposit license was used to authorize these bytes.
Older records remain preserved rather than retroactively rewritten.

## Acquisition feasibility and comparison

Required official archive:
https://physionet.org/files/cgmacros/1.0.0/CGMacros_dateshifted365.zip
— 657,187,340 bytes (release display 626.7 MB). The release-wide downloadable ZIP
is a different wrapper, displayed as 627.1 MB; do not compare its hash to the inner
archive. Release files total 627.9 MB as displayed by PhysioNet.

The local 54-input manifest comprises 48 archive members (45 participant CSVs and
`bio.csv`, `microbes.csv`, `gut_health_test.csv`) plus four dictionary CSVs,
`SHA256SUMS.txt` and the empty `LICENSE.txt`. It excludes photographs. The release
also supplies `DataDictionary.pdf`, which is not one of these 54 required inputs.
Expected archive members come from the existing manifest, not a newly inspected ZIP.

[Current published checksums](https://physionet.org/files/cgmacros/1.0.0/SHA256SUMS.txt)
agree with the manifest's expected archive digest
`05c8b0e6f1a2757050aced55ce4bf6ab2ac9b30f2fd8ca193056812d9c621d4d`
and all four dictionary digests plus the empty license-file digest. This is
metadata agreement, **not verification of downloaded input bytes**. The historical
manifest explicitly says the full archive was never hash-verified. All 48 member
hashes and all six companion-file hashes must be checked after acquisition.

No patient data was acquired. The organizer-rights question remains material to
the integrated competition route, so acquisition was deferred as instructed.
Only public web metadata was inspected. A separate shell fetch of checksum
metadata was denied by the environment's network socket restriction; browser-tool
retrieval succeeded. No access requirement was bypassed. Preserve the full web
license and attribution separately: the release's empty LICENSE.txt is insufficient.

## Unsent clarification request

To the Happiest Health Digital Twin Challenge organizer through its official
challenge contact channel:

> We are entering a student research prototype using CGMacros v1.0.0 under
> CC BY-NC-SA 4.0. Please provide the applicable submission/IP terms and confirm
> whether public independent MIT code, a synthetic demonstration and attributed
> aggregate research findings are acceptable while participant data and weights
> remain excluded. Do entrants grant any commercialization, sublicensing or IP
> assignment rights over third-party-derived material, or only rights to evaluate
> and publicize the submitted presentation? Does your website section 5 apply to
> this Unstop submission and its linked repository?

No message was sent. If the response requires rights beyond NC-SA for protected
CGMacros material, ask the dataset licensors about **those specific rights**;
do not request an unnecessary blanket research permission letter.

## Separate new-experiment route (not executed)

After scope/terms are resolved, verify authorized release bytes against publisher
and historical member hashes. Freeze a new protocol, source checkpoint, runtime,
input manifest and Stage 1 audit specification before evaluation. Recover the
original Stage 1 audit helpers or implement/review explicit rules from the audit
documentation and source contracts; validate them independently. Newly computed
tables are new audit evidence, never replacements for original hash-pinned tables.

Reuse participant-disjoint splits and frozen sensor-only Ridge selections without
reselection. Generate new held-out reference predictions with training-only
preprocessing; decide explicitly whether the new study needs only 14 Ridge fits
or additional frozen comparators. Do not invoke the 728-fit search implicitly.
Keep Stage 4's 48-hour adaptation and Stage 5's 24-hour offset plus following
24-hour calibration, purges and delayed evaluation separate. Freeze and label
new references before downstream comparisons; retain independent correctness
checks rather than treating self-agreement as historical reproduction.

Use isolated versioned outputs and a separate new-experiment verifier/entry point.
Do not relax `regenerate_replay.py` or the historical Stage 2–5 hash/comparison
gates. Missing originals preclude original-result reproduction. Released,
interpolated minute data remain retrospective research inputs, not proof of
native real-time forecasting or clinical benefit.

No patient training, source changes, staging, commit, push or deployment occurred.
Only this review document was added; earlier work remains preserved.

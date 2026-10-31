# Enterprise document corpus: 25 golden questions and reference answers

Prepared from the user-supplied enterprise-document-corpus.zip snapshots on 2026-10-31. All 16 original documents are represented. These are authored reference labels, not system responses or measured evaluation results.

17 development cases; 8 frozen held-out cases. Reserve held-out questions and answers for final evaluation. Answers describe the supplied document snapshots, not independently verified current services or private account state.

## 1. Where should a user already registered for Microsoft Entra self-service password reset go to reset a forgotten password, and what if IT has not enabled self-service reset?

**Reference answer:** Go to https://aka.ms/sspr. If IT has not enabled self-service password reset, contact the help desk for assistance.

**Case:** enterprise_01 | **Split:** development | **Type:** direct

**Evidence:**

- [entra-concept-sspr-howitworks](https://raw.githubusercontent.com/MicrosoftDocs/entra-docs/7f78b50dce9d8cf119de57cbd6fd66e24a6c58d4/docs/identity/authentication/concept-sspr-howitworks.md), How it works: Microsoft Entra self-service password reset; extracted-text lines 15-17. Reference ID: `ref_997b1cef7a7d9de1`.

**Grading note:** Assumes an already registered end user; do not promise SSPR access when the organization has not enabled it.

## 2. An Entra SSPR policy changes from one required verification method to two. A user has only one method registered. Can that user still reset or unlock the account?

**Reference answer:** No. With two verification methods required and only one registered, the user cannot reset or unlock the account. At least two properly configured methods are needed under that policy.

**Case:** enterprise_02 | **Split:** development | **Type:** scenario

**Evidence:**

- [entra-concept-sspr-howitworks](https://raw.githubusercontent.com/MicrosoftDocs/entra-docs/7f78b50dce9d8cf119de57cbd6fd66e24a6c58d4/docs/identity/authentication/concept-sspr-howitworks.md), Change authentication methods; extracted-text lines 186-192. Reference ID: `ref_960fb4804531607e`.

**Grading note:** Preserve the one-versus-two-method distinction in the source table.

## 3. For accounts created and managed directly in Microsoft Entra ID, what password length and character-type requirements are listed in the password policy?

**Reference answer:** Passwords must contain 8 to 256 characters and use at least three of four character types: lowercase letters, uppercase letters, numbers, and symbols.

**Case:** enterprise_03 | **Split:** heldout | **Type:** direct

**Evidence:**

- [entra-concept-sspr-policy](https://raw.githubusercontent.com/MicrosoftDocs/entra-docs/7f78b50dce9d8cf119de57cbd6fd66e24a6c58d4/docs/identity/authentication/concept-sspr-policy.md), Microsoft Entra password policies; extracted-text lines 43-43. Reference ID: `ref_f8ac73a4bdeb5049`.

**Grading note:** Scope is directly managed Entra accounts; do not generalize this table to all on-premises password policies.

## 4. Under the administrator two-gate SSPR policy, how many pieces of authentication data are required, and can security questions be used?

**Reference answer:** Two pieces of authentication data are required, such as an email address, an authenticator app, or a phone number. Security questions are prohibited.

**Case:** enterprise_04 | **Split:** development | **Type:** direct

**Evidence:**

- [entra-concept-sspr-policy](https://raw.githubusercontent.com/MicrosoftDocs/entra-docs/7f78b50dce9d8cf119de57cbd6fd66e24a6c58d4/docs/identity/authentication/concept-sspr-policy.md), Administrator reset policy differences; extracted-text lines 68-68. Reference ID: `ref_9ef4b51a4b3a15cf`.

**Grading note:** This question is conditional on the two-gate policy; it does not ask whether administrator SSPR is enabled by default.

## 5. According to the Entra SSPR troubleshooting guide, what should be checked when an administrator cannot see Password reset under Protection?

**Reference answer:** Check whether a Microsoft Entra ID license is assigned to the administrator performing the operation. The guide identifies a missing license on that administrator as the reason the Password reset option is not visible.

**Case:** enterprise_05 | **Split:** development | **Type:** scenario

**Evidence:**

- [entra-troubleshoot-sspr](https://raw.githubusercontent.com/MicrosoftDocs/entra-docs/7f78b50dce9d8cf119de57cbd6fd66e24a6c58d4/docs/identity/authentication/troubleshoot-sspr.md), I don't see Password reset under Protection in the Microsoft Entra admin center; extracted-text lines 24-24. Reference ID: `ref_05808ea4328d45c4`.

**Grading note:** The license belongs to the administrator performing the operation, not merely to the target user.

## 6. My Entra password-reset phone call never arrives, and my directory phone number includes an extension. What does the troubleshooting guide say to fix?

**Reference answer:** Check that the directory phone number is correctly formatted, for example +1 4251234567. Password reset does not support extensions and strips them before calling. Use a number without an extension or integrate the extension into the phone number in the PBX.

**Case:** enterprise_06 | **Split:** heldout | **Type:** paraphrase

**Evidence:**

- [entra-troubleshoot-sspr](https://raw.githubusercontent.com/MicrosoftDocs/entra-docs/7f78b50dce9d8cf119de57cbd6fd66e24a6c58d4/docs/identity/authentication/troubleshoot-sspr.md), SSPR usage; extracted-text lines 94-94. Reference ID: `ref_275421631a678ada`.

**Grading note:** Do not claim that adding an extension to the directory number is supported.

## 7. For Microsoft Entra Connect version 1.1.443.0 or later in the global Azure cloud, which outbound HTTPS destinations are required for password writeback?

**Reference answer:** Outbound HTTPS access is required to *.passwordreset.microsoftonline.com and *.servicebus.windows.net.

**Case:** enterprise_07 | **Split:** development | **Type:** direct

**Evidence:**

- [entra-troubleshoot-sspr-writeback](https://raw.githubusercontent.com/MicrosoftDocs/entra-docs/7f78b50dce9d8cf119de57cbd6fd66e24a6c58d4/docs/identity/authentication/troubleshoot-sspr-writeback.md), Confirm network connectivity; extracted-text lines 31-34. Reference ID: `ref_744f3654fb716ec2`.

**Grading note:** Use global-cloud endpoints; do not substitute US Government or China endpoints.

## 8. Which event IDs help identify the service bus listener for Entra password-writeback troubleshooting, and how can its port connectivity be tested?

**Reference answer:** On the Entra Connect server, inspect the Windows Application event log for event ID 31034 or 31019 and identify the service bus listener namespace. Test it with Test-NetConnection -ComputerName <namespace>.servicebus.windows.net -Port 443.

**Case:** enterprise_08 | **Split:** development | **Type:** scenario

**Evidence:**

- [entra-troubleshoot-sspr-writeback](https://raw.githubusercontent.com/MicrosoftDocs/entra-docs/7f78b50dce9d8cf119de57cbd6fd66e24a6c58d4/docs/identity/authentication/troubleshoot-sspr-writeback.md), Confirm network connectivity; extracted-text lines 54-55. Reference ID: `ref_e1a9758c6c3b995a`.
- [entra-troubleshoot-sspr-writeback](https://raw.githubusercontent.com/MicrosoftDocs/entra-docs/7f78b50dce9d8cf119de57cbd6fd66e24a6c58d4/docs/identity/authentication/troubleshoot-sspr-writeback.md), Confirm network connectivity; extracted-text lines 62-62. Reference ID: `ref_edab3a71d85310b7`.

**Grading note:** The namespace comes from the event log. The linked screenshot is not required as evidence.

## 9. Can an Azure subscription with pay-as-you-go pricing enable a spending limit?

**Reference answer:** No. Spending limits are unavailable for pay-as-you-go subscriptions and subscriptions with commitment plans. The portal does not show a spending limit for these subscriptions, and one cannot be enabled.

**Case:** enterprise_09 | **Split:** development | **Type:** direct

**Evidence:**

- [azure-spending-limit](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit), Azure spending limit; extracted-text lines 20-20. Reference ID: `ref_ac2c6b5820f77287`.

**Grading note:** Do not confuse a spending limit with a budget alert or promise a configurable cap.

## 10. If I leave the Azure spending limit enabled, does that guarantee that every type of charge is blocked?

**Reference answer:** No. Some external services published in Azure Marketplace cannot use subscription credits and can incur separate charges even when a spending limit is set. Examples listed include Visual Studio licenses, Microsoft Entra ID P1 or P2, support plans, and most third-party branded services.

**Case:** enterprise_10 | **Split:** development | **Type:** paraphrase

**Evidence:**

- [azure-spending-limit](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/spending-limit), A spending limit doesn't prevent all charges; extracted-text lines 58-58. Reference ID: `ref_553f8be5f1a7f74e`.

**Grading note:** Preserve the exception; the spending limit is not an absolute guarantee against all charges.

## 11. For an Azure MOSP subscription invoice, who can download it, and are subscription Owner, Contributor, or Reader roles sufficient by themselves?

**Reference answer:** The subscription account administrator can download the invoice. Users with subscription Owner, Contributor, or Reader roles can download it only if the account administrator grants permission; those roles alone are not sufficient.

**Case:** enterprise_11 | **Split:** development | **Type:** direct

**Evidence:**

- [azure-invoice](https://learn.microsoft.com/en-us/azure/cost-management-billing/understand/download-azure-invoice), Download your MOSP Azure subscription invoice; extracted-text lines 45-45. Reference ID: `ref_666af88e8a81252e`.

**Grading note:** Apply the MOSP rules, not the different MCA/MPA billing-profile permissions.

## 12. Which roles allow downloading an Azure MCA or MPA billing-profile invoice, and who can download invoices for all billing profiles in an account?

**Reference answer:** An Owner, Contributor, Reader, or Invoice Manager on the billing profile can download that profile's invoice. An Owner, Contributor, or Reader on the billing account can download invoices for every billing profile in that account.

**Case:** enterprise_12 | **Split:** development | **Type:** direct

**Evidence:**

- [azure-invoice](https://learn.microsoft.com/en-us/azure/cost-management-billing/understand/download-azure-invoice), Download an MCA or MPA billing profile invoice; extracted-text lines 86-86. Reference ID: `ref_3a57a0356d89743b`.

**Grading note:** Keep billing-profile scope separate from billing-account scope and subscription-level roles.

## 13. After paying a past-due Azure balance, how long can subscription reactivation take, and when should a continuing resource-management delay be escalated?

**Reference answer:** Reactivation can take up to 24 hours after payment. Once the subscription is reactivated, if a delay in creating or managing resources exceeds 30 minutes, contact Azure Billing Support. Most resources resume automatically, but check them and restart them if needed.

**Case:** enterprise_13 | **Split:** heldout | **Type:** scenario

**Evidence:**

- [azure-disabled-subscription](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/subscription-disabled), Reactivation process time / After reactivation; extracted-text lines 44-46. Reference ID: `ref_d19cdddabc69ffec`.

**Grading note:** The 24-hour window starts after payment; the 30-minute escalation concerns a delay after reactivation.

## 14. Does requesting an Azure quota increase itself cost money, and does an assigned adjustable quota guarantee resource capacity?

**Reference answer:** There is no charge for requesting a quota increase; charges depend on resource usage. An adjustable-quota increase is subject to Microsoft's review, including usage, service availability, and capacity constraints. An assigned quota does not reserve or guarantee capacity.

**Case:** enterprise_14 | **Split:** heldout | **Type:** multi_evidence

**Evidence:**

- [azure-quotas](https://learn.microsoft.com/en-us/azure/quotas/quotas-overview), Quotas or limits?; extracted-text lines 24-24. Reference ID: `ref_7120b17613a2fbe0`.
- [azure-quotas](https://learn.microsoft.com/en-us/azure/quotas/quotas-overview), Adjustable and non-adjustable quotas; extracted-text lines 29-29. Reference ID: `ref_3704b5f907422f19`.

**Grading note:** Do not turn the no-fee statement into a claim that consumed resources are free or that increases are automatically approved.

## 15. Under RFC 6749 section 4.1.2, how long should an authorization code live, and what must happen if it is used more than once?

**Reference answer:** The code must expire shortly after issuance; a maximum lifetime of 10 minutes is recommended. The client must not use it more than once. If it is reused, the authorization server must deny the request and should revoke, when possible, all tokens previously issued from that code.

**Case:** enterprise_15 | **Split:** development | **Type:** direct

**Evidence:**

- [ietf-rfc-6749](https://www.rfc-editor.org/rfc/rfc6749.txt), 4.1.2. Authorization Response; extracted-text lines 1449-1467. Reference ID: `ref_0d110132a0a01f3c`.

**Grading note:** Ten minutes is a recommended maximum, not a mandatory fixed lifetime; denial is MUST and related-token revocation is SHOULD.

## 16. In an RFC 7009 token revocation request, which body parameter is required, which token-type hint is optional, and what happens if the hint does not locate the token?

**Reference answer:** The token parameter is required, while token_type_hint is optional. The request body uses application/x-www-form-urlencoded. If the server cannot find the token using the hint, it must search across all token types it supports; it may also ignore the hint.

**Case:** enterprise_16 | **Split:** development | **Type:** direct

**Evidence:**

- [ietf-rfc-7009](https://www.rfc-editor.org/rfc/rfc7009.txt), 2.1. Revocation Request; extracted-text lines 191-211. Reference ID: `ref_f89b0fa4fa1b5fcf`.

**Grading note:** Do not require token_type_hint or limit token lookup to the hinted type.

## 17. A client sends an invalid token to an RFC 7009 revocation endpoint. Should the endpoint return an invalid-token error?

**Reference answer:** No. The server returns HTTP 200 both when revocation succeeds and when the submitted token is invalid. Invalid tokens do not cause an error response, and the client ignores the response body. An invalid token_type_hint value is also ignored.

**Case:** enterprise_17 | **Split:** development | **Type:** scenario

**Evidence:**

- [ietf-rfc-7009](https://www.rfc-editor.org/rfc/rfc7009.txt), 2.2. Revocation Response; extracted-text lines 275-296. Reference ID: `ref_c6d90129995421a3`.

**Grading note:** This is about an invalid token or hint, not invalid client authentication or an unsupported token type.

## 18. Under RFC 7662, what should an authorized introspection response contain when the token is inactive, unknown, or not available for that protected resource to introspect?

**Reference answer:** The authorization server must return active set to false. To avoid disclosing its state, it should not provide additional information about the inactive token, including the reason it is inactive.

**Case:** enterprise_18 | **Split:** heldout | **Type:** scenario

**Evidence:**

- [ietf-rfc-7662](https://www.rfc-editor.org/rfc/rfc7662.txt), 2.2. Introspection Response; extracted-text lines 420-427. Reference ID: `ref_e805dc9a8744ff23`.

**Grading note:** The introspection request itself is properly authorized; do not confuse this response with a failed client-authentication error.

## 19. For the RFC 8628 device authorization flow, how should a client poll after authorization_pending, and how does slow_down change the interval?

**Reference answer:** After authorization_pending, the client should keep polling but must wait at least the interval supplied in the device authorization response, or 5 seconds if none was supplied. After slow_down, polling can continue, but the interval must increase by 5 seconds for that request and all subsequent requests.

**Case:** enterprise_19 | **Split:** heldout | **Type:** scenario

**Evidence:**

- [ietf-rfc-8628](https://www.rfc-editor.org/rfc/rfc8628.txt), 3.5. Device Access Token Response; extracted-text lines 588-602. Reference ID: `ref_36b9902d4a7ace8a`.

**Grading note:** slow_down adds 5 seconds to the interval; it does not mean set every interval to 5 seconds.

## 20. According to RFC 9068, must JWT access tokens be signed, may they use alg=none, and which signature algorithm must conforming servers support?

**Reference answer:** JWT access tokens must be signed and must not use none as the signing algorithm. Conforming authorization servers and resource servers must support RS256. Asymmetric cryptography is recommended, rather than being the only signing approach the profile permits.

**Case:** enterprise_20 | **Split:** development | **Type:** direct

**Evidence:**

- [ietf-rfc-9068](https://www.rfc-editor.org/rfc/rfc9068.pdf), 2.1. Header; physical PDF page 4, extracted-text lines 16-21. Reference ID: `ref_283ee20004e1b64d`.

**Grading note:** Distinguish mandatory RS256 support from a requirement that every token be signed with RS256.

## 21. What typ header value does RFC 9068 recommend for JWT access tokens, and why explicitly distinguish them from ID tokens?

**Reference answer:** The recommended typ value is at+jwt, omitting the application/ prefix from application/at+jwt. Explicit access-token typing helps prevent a resource server from accepting an OpenID Connect ID token as an access token.

**Case:** enterprise_21 | **Split:** development | **Type:** direct

**Evidence:**

- [ietf-rfc-9068](https://www.rfc-editor.org/rfc/rfc9068.pdf), 2.1. Header; physical PDF page 4, extracted-text lines 22-29. Reference ID: `ref_7924d454e7e3c977`.

**Grading note:** Do not replace the access-token type with the generic JWT type or claim that ID tokens are interchangeable with access tokens.

## 22. What does a successful RFC 9126 pushed authorization request return, and what restrictions apply to the request_uri?

**Reference answer:** The server returns HTTP 201 with a JSON response containing request_uri and expires_in. request_uri is a single-use reference to the posted authorization request and must be bound to the client that posted it. expires_in is its lifetime in seconds as a positive integer; the server chooses the lifetime, which is typically short, for example 5 to 600 seconds.

**Case:** enterprise_22 | **Split:** development | **Type:** direct

**Evidence:**

- [ietf-rfc-9126](https://www.rfc-editor.org/rfc/rfc9126.pdf), 2.2. Successful Response; physical PDF page 8, extracted-text lines 14-27. Reference ID: `ref_e8745f67422f668d`.
- [ietf-rfc-9126](https://www.rfc-editor.org/rfc/rfc9126.pdf), 2.2. Successful Response; physical PDF page 8, extracted-text lines 34-34. Reference ID: `ref_2be3649227e9b04f`.

**Grading note:** The 5-to-600-second range is an example of typical lifetimes, not a mandatory allowed range.

## 23. Which JOSE header fields must an RFC 9449 DPoP proof JWT contain, and what algorithm and key-content restrictions apply?

**Reference answer:** It must contain typ with value dpop+jwt, alg identifying an asymmetric JWS signature algorithm, and jwk containing the client's public key. alg must not be none or a symmetric MAC algorithm, and jwk must not contain a private key.

**Case:** enterprise_23 | **Split:** heldout | **Type:** direct

**Evidence:**

- [ietf-rfc-9449](https://www.rfc-editor.org/rfc/rfc9449.pdf), 4.2. DPoP Proof JWT Syntax; physical PDF page 9, extracted-text lines 7-16. Reference ID: `ref_81ef862ef936b89d`.

**Grading note:** The DPoP header carries a public key, never the signing private key.

## 24. In RFC 9449, what do htm, htu, and iat identify in a DPoP proof, and how is ath calculated when an access token is presented to a protected resource?

**Reference answer:** htm identifies the HTTP method, htu identifies the target URI without query or fragment, and iat is the proof's creation timestamp. When the proof accompanies an access token for protected-resource access, ath is also required: it is the base64url-encoded SHA-256 hash of the ASCII encoding of the access token's value.

**Case:** enterprise_24 | **Split:** heldout | **Type:** direct

**Evidence:**

- [ietf-rfc-9449](https://www.rfc-editor.org/rfc/rfc9449.pdf), 4.2. DPoP Proof JWT Syntax; physical PDF page 9, extracted-text lines 24-33. Reference ID: `ref_ff53000c72e59300`.

**Grading note:** ath is conditional on presenting an access token to a protected resource, not a blanket claim about every proof context.

## 25. How did guidance on the OAuth resource owner password credentials grant change from RFC 6749 section 4.3 to RFC 9700 section 2.4?

**Reference answer:** RFC 6749 described the password credentials grant for cases where the resource owner trusts the client and other flows are not viable. RFC 9700 updates the guidance and says the grant must not be used because it exposes user credentials to clients, expands the attack surface, and is not designed for two-factor authentication or multi-step authentication. This is newer security guidance superseding the older allowance, not two equally current policies to choose between.

**Case:** enterprise_25 | **Split:** development | **Type:** guidance_update

**Evidence:**

- [ietf-rfc-6749](https://www.rfc-editor.org/rfc/rfc6749.txt), 4.3. Resource Owner Password Credentials Grant; extracted-text lines 2068-2081. Reference ID: `ref_731fdb1cf57270ef`.
- [ietf-rfc-9700](https://www.rfc-editor.org/rfc/rfc9700.pdf), 2.4. Resource Owner Password Credentials Grant; physical PDF page 10, extracted-text lines 3-12. Reference ID: `ref_fb340e4752ed2035`.

**Grading note:** RFC numbers identify standards documents, not software releases. Preserve MUST NOT in the newer guidance and do not present the historical grant as recommended.

## Provenance and use

Exact source excerpts and locations are in cases.json; source hashes, metadata, and original publisher URLs are in provenance.json. Line numbers refer to extracted text (or a PDF page's extracted text), not raw HTML. The JSONL exports use Ragas SingleTurnSample reference fields. Add the actual pipeline response and retrieved_contexts when evaluating; never substitute these gold contexts as if they were retrieval results.

Reference context IDs are evaluation evidence IDs, not EvidenceDesk chunk IDs. Map them to real ingestion passage IDs before using ID-based retrieval metrics. No scoring, provider setup, or Ragas execution was performed.

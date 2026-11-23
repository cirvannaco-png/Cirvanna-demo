# Cirvanna iOS authentication integration

This is the native-client contract for the future Cirvanna iOS app. The repository currently has no Xcode project, bundle identifier, entitlements or Apple Developer provisioning, so this document does not claim that a shippable iOS app exists.

## Recommended native architecture

Use the official Supabase Swift client in the iOS app:
- Apple: native AuthenticationServices credential, exchanged with `signInWithIdToken`.
- Microsoft: Supabase Azure OAuth using the Swift client's OAuth flow and an app callback URL handled by `ASWebAuthenticationSession`.
- Google: use the same OAuth/deep-link pattern or a native Google credential exchange if selected later.
- Email: use Supabase email OTP with a native confirmation screen; do not embed a service key in the app.

The iOS client stores its own session using the SDK's supported iOS storage. For BFF API calls, send the short-lived Supabase access token in the HTTPS Authorization header. The BFF independently verifies the JWT signature, issuer, audience, expiry and `app_role`; it never trusts a client-supplied role. Do not copy the refresh token into application logs, analytics, crash reports or general-purpose preferences.

## Native Apple sign-in

Enable the **Sign in with Apple** capability for the actual App ID/bundle identifier in Apple Developer. Generate a cryptographically random raw nonce for each attempt, send its SHA-256 hash to Apple, and pass the original raw nonce to Supabase for validation.

```swift
import AuthenticationServices
import CryptoKit
import Supabase

func sha256(_ value: String) -> String {
    let digest = SHA256.hash(data: Data(value.utf8))
    return digest.map { String(format: "%02x", $0) }.joined()
}

func signInWithApple(
    supabase: SupabaseClient,
    rawNonce: String,
    identityToken: String
) async throws {
    _ = try await supabase.auth.signInWithIdToken(
        credentials: OpenIDConnectCredentials(
            provider: .apple,
            idToken: identityToken,
            nonce: rawNonce
        )
    )
}

// When creating the ASAuthorizationAppleIDRequest:
let rawNonce = /* cryptographically random, one-use value */
request.nonce = sha256(rawNonce)

// In the ASAuthorizationController completion handler:
// 1. Extract ASAuthorizationAppleIDCredential.identityToken.
// 2. Convert it to UTF-8 text.
// 3. Call signInWithApple(supabase:rawNonce:identityToken:).
// 4. Persist the first-sign-in full name only if Apple supplied it.
// 5. Discard the raw nonce after the exchange.
```

Apple returns a person's full name only on the first authorization. If the product needs it, capture it from the native credential on that first sign-in and save it to the user's profile through a trusted, validated profile update. Do not assume it will appear in later ID tokens.

## Microsoft Entra ID on iOS

Supabase identifies Microsoft as the `azure` provider. Configure the Azure provider in Supabase Auth, register the Supabase callback URI with the Entra application, and select the intended account types (work/school only, personal Microsoft accounts, or both) deliberately.

Use the Swift SDK's OAuth flow with the app's registered callback URL and handle the returned URL through the SDK's session exchange. Register the callback scheme in the iOS app's URL Types and test the full flow on physical devices. The exact scheme must be chosen only after the final bundle identifier and app URL scheme are confirmed.

```swift
// Provider name is Azure in Supabase, although the user-facing label is Microsoft.
let session = try await supabase.auth.signInWithOAuth(provider: .azure) { (authSession: ASWebAuthenticationSession) in
    // Customize the system authentication session if required.
    authSession.prefersEphemeralWebBrowserSession = false
}
```

Do not use an arbitrary WebView for Microsoft authentication. Use the system authentication session so the platform can enforce the expected browser security boundary.

## Optional BFF cookie bridge

For an iOS experience that embeds the BFF-hosted web UI, the BFF also exposes:

`POST /auth/ios/apple`

Request body:
- `id_token`: Apple identity token from AuthenticationServices.
- `nonce`: original raw nonce used to create the Apple request.

The BFF exchanges the token with Supabase, verifies the resulting Supabase JWT against the configured JWKS, encrypts the access/refresh token pair in `auth_private.sessions`, and returns an opaque HttpOnly/Secure cookie. The native app must retain that cookie in a protected cookie store if it uses this bridge. Prefer the native Supabase SDK session for a fully native app unless a shared BFF cookie is specifically required.

## Release checklist

- [ ] Confirm Apple Developer Team, App ID and final bundle identifier.
- [ ] Enable Sign in with Apple entitlement and test first-time and returning users.
- [ ] Configure the Apple provider in Supabase; include both the Services ID and native App ID when web and native sign-in are both enabled.
- [ ] Configure Microsoft Entra application, supported account types, client ID/secret and Supabase callback.
- [ ] Register the iOS URL scheme / universal-link callback for Microsoft OAuth.
- [ ] Store the Supabase publishable key in app configuration; never ship a service-role or secret key.
- [ ] Verify Keychain/session persistence, refresh, sign-out, revoked-provider behavior and account switching on physical iOS devices.
- [ ] Confirm BFF authorization works with a real Supabase-issued access token and rejects expired, wrong-issuer, wrong-audience and tampered tokens.
- [ ] Complete privacy disclosures, Apple App Review requirements and accessibility QA.

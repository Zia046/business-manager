package com.burhannexus.companion;

import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.spec.ECGenParameterSpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;

import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.Mac;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * Pairing and encryption, the same scheme as app/services/companion.py on the PC:
 * P-256 key exchange, the 6-digit code mixed into the key (HKDF-SHA256), then AES-256-GCM for every message.
 */
public final class Crypto {
    private Crypto() {}

    public static KeyPair newKeyPair() throws Exception {
        KeyPairGenerator g = KeyPairGenerator.getInstance("EC");
        g.initialize(new ECGenParameterSpec("secp256r1"));
        return g.generateKeyPair();
    }

    public static String b64(byte[] b) {
        return Base64.getEncoder().encodeToString(b);
    }

    public static byte[] unb64(String s) {
        return Base64.getDecoder().decode(s);
    }

    public static byte[] sharedSecret(PrivateKey mine, byte[] serverPublicDer) throws Exception {
        PublicKey theirs = KeyFactory.getInstance("EC").generatePublic(new X509EncodedKeySpec(serverPublicDer));
        KeyAgreement ka = KeyAgreement.getInstance("ECDH");
        ka.init(mine);
        ka.doPhase(theirs, true);
        return ka.generateSecret();
    }

    private static byte[] hmac(byte[] key, byte[] data) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(data);
    }

    /** HKDF-SHA256 with a 32-byte output (one block). */
    static byte[] hkdf(byte[] ikm, byte[] salt, byte[] info) throws Exception {
        byte[] prk = hmac(salt, ikm);
        byte[] t = new byte[info.length + 1];
        System.arraycopy(info, 0, t, 0, info.length);
        t[info.length] = 1;
        return hmac(prk, t);
    }

    public static byte[] sessionKey(byte[] shared, String code, String deviceId) throws Exception {
        byte[] salt = MessageDigest.getInstance("SHA-256")
                .digest(("BNBC1|" + code + "|" + deviceId).getBytes(StandardCharsets.UTF_8));
        return hkdf(shared, salt, "bnbc-session".getBytes(StandardCharsets.UTF_8));
    }

    public static String proof(byte[] key, String text) throws Exception {
        byte[] m = hmac(key, text.getBytes(StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        for (byte x : m) sb.append(String.format("%02x", x));
        return sb.toString();
    }

    /** Returns {nonce, ciphertext}, both base64. */
    public static String[] seal(byte[] key, String deviceId, byte[] plain) throws Exception {
        byte[] nonce = new byte[12];
        new SecureRandom().nextBytes(nonce);
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, nonce));
        c.updateAAD(deviceId.getBytes(StandardCharsets.UTF_8));
        return new String[] {b64(nonce), b64(c.doFinal(plain))};
    }

    public static byte[] open(byte[] key, String deviceId, String nonce, String cipherText) throws Exception {
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, unb64(nonce)));
        c.updateAAD(deviceId.getBytes(StandardCharsets.UTF_8));
        return c.doFinal(unb64(cipherText));
    }
}

import com.burhannexus.companion.Crypto;
import com.burhannexus.companion.Template;

import java.nio.charset.StandardCharsets;
import java.security.KeyPair;

/** Runs the Android app's own Crypto / Template classes on a desktop JVM so the tests can check them against the PC. */
public class Interop {
    public static void main(String[] a) throws Exception {
        if (a[0].equals("pair")) {                  // pair <serverPubB64> <code> <deviceId> <plaintext>
            KeyPair kp = Crypto.newKeyPair();
            byte[] key = Crypto.sessionKey(Crypto.sharedSecret(kp.getPrivate(), Crypto.unb64(a[1])), a[2], a[3]);
            String[] sealed = Crypto.seal(key, a[3], a[4].getBytes(StandardCharsets.UTF_8));
            System.out.println(Crypto.b64(kp.getPublic().getEncoded()));
            System.out.println(Crypto.proof(key, "pair|" + a[3]));
            System.out.println(Crypto.b64(key));
            System.out.println(sealed[0]);
            System.out.println(sealed[1]);
        } else if (a[0].equals("open")) {           // open <keyB64> <deviceId> <nonce> <cipher>
            System.out.println(new String(Crypto.open(Crypto.unb64(a[1]), a[2], a[3], a[4]), StandardCharsets.UTF_8));
        } else if (a[0].equals("proof")) {          // proof <keyB64> <text>
            System.out.println(Crypto.proof(Crypto.unb64(a[1]), a[2]));
        } else {                                    // render <amount> <templateB64>
            String out = Template.render(new String(Crypto.unb64(a[2]), StandardCharsets.UTF_8), Double.parseDouble(a[1]));
            System.out.println(out == null ? "<null>" : Crypto.b64(out.getBytes(StandardCharsets.UTF_8)));
        }
    }
}

/** Runs on a plain JVM: no Android, no device, no emulator. */
public class PairingTest {
    private static int failed = 0;

    static void eq(String what, String got, String want) {
        if (want.equals(got)) { System.out.println("  ok   " + what); }
        else { failed++; System.out.println("  FAIL " + what + "\n       got  " + got
                                            + "\n       want " + want); }
    }

    public static void main(String[] args) {
        System.out.println("Pairing.buildUrl");
        eq("bare IP gets the default port and a code",
           tw.lagscope.viewer.Pairing.buildUrl("192.168.0.10", "4821"),
           "http://192.168.0.10:23125/?key=4821");
        eq("an explicit port is left alone",
           tw.lagscope.viewer.Pairing.buildUrl("192.168.0.10:8080", "4821"),
           "http://192.168.0.10:8080/?key=4821");
        eq("no code is fine",
           tw.lagscope.viewer.Pairing.buildUrl("192.168.0.10", ""),
           "http://192.168.0.10:23125/");
        eq("a pasted URL is used as-is",
           tw.lagscope.viewer.Pairing.buildUrl("http://192.168.0.10:23125/?key=4821", ""),
           "http://192.168.0.10:23125/?key=4821");
        eq("a pasted URL that already has a code does not get a second one",
           tw.lagscope.viewer.Pairing.buildUrl("http://192.168.0.10:23125/?key=4821", "9999"),
           "http://192.168.0.10:23125/?key=4821");
        eq("a pasted URL without a code takes the typed one",
           tw.lagscope.viewer.Pairing.buildUrl("http://192.168.0.10:23125/", "4821"),
           "http://192.168.0.10:23125/?key=4821");
        eq("whitespace from a paste is trimmed",
           tw.lagscope.viewer.Pairing.buildUrl("  192.168.0.10  ", " 4821 "),
           "http://192.168.0.10:23125/?key=4821");
        eq("nothing typed produces nothing, not a broken URL",
           tw.lagscope.viewer.Pairing.buildUrl("", "4821"), "");
        eq("null is not a crash",
           tw.lagscope.viewer.Pairing.buildUrl(null, null), "");
        eq("a hostname works as well as an IP",
           tw.lagscope.viewer.Pairing.buildUrl("my-pc.local", "1234"),
           "http://my-pc.local:23125/?key=1234");

        // The name has to be the one web.py reads. It was "code" here and
        // "key" there, so filling the two fields separately built a URL the
        // server answered with 403 - which is what a user actually hit.
        eq("the parameter is the one the server reads",
           tw.lagscope.viewer.Pairing.QUERY_KEY, "key");
        eq("a pasted url is not given a second access code",
           tw.lagscope.viewer.Pairing.buildUrl("http://192.168.0.10:23125/?key=4821", "9999"),
           "http://192.168.0.10:23125/?key=4821");

        System.out.println(failed == 0 ? "\nall passed" : "\n" + failed + " failed");
        System.exit(failed == 0 ? 0 : 1);
    }
}

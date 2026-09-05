package tw.lagscope.viewer;

/**
 * Turning what someone types into the dashboard URL.
 *
 * Kept apart from the Activity because it is the only part with a right and a
 * wrong answer, and separating it is what makes it testable without a phone -
 * this was written on a machine with no Android device and no emulator, so
 * anything that cannot be checked here cannot be checked at all.
 */
public final class Pairing {

    /** The port the desktop app serves the dashboard on by default. */
    public static final int DEFAULT_PORT = 23125;

    /**
     * The query parameter the desktop server reads the access code from.
     *
     * This has to be the name web.py checks, not a name that merely reads
     * well. It was "code" here and "key" there, so filling the two fields on
     * the pairing screen separately - the obvious thing to do, given how they
     * are labelled - built a URL the server answered with 403 and the page
     * rendered as "access code incorrect". Pasting the whole URL happened to
     * work, which is why it survived: the one path that was documented was
     * the one path that did not go through this.
     */
    public static final String QUERY_KEY = "key";

    private Pairing() { }

    /** Accepts a pasted dashboard URL as readily as a host and a code. */
    public static String buildUrl(String address, String code) {
        String host = address == null ? "" : address.trim();
        String pin = code == null ? "" : code.trim();
        if (host.isEmpty()) {
            return "";
        }

        // A pasted URL already carries everything, including its own code;
        // appending a second one would produce a request the server rejects.
        if (host.startsWith("http://") || host.startsWith("https://")) {
            if (pin.isEmpty() || host.contains(QUERY_KEY + "=")) {
                return host;
            }
            return host + (host.contains("?") ? "&" : "?") + QUERY_KEY + "=" + pin;
        }

        // A bare host, or host:port. Filling in the default port removes the
        // detail that is easiest to get wrong when copying by hand.
        if (host.indexOf(':') < 0) {
            host = host + ":" + DEFAULT_PORT;
        }
        String url = "http://" + host + "/";
        if (!pin.isEmpty()) {
            url = url + "?" + QUERY_KEY + "=" + pin;
        }
        return url;
    }
}

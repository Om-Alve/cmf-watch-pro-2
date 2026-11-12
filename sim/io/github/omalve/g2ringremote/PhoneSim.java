package io.github.omalve.g2ringremote;

import java.io.File;
import java.io.FileWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Stands in for the phone: replays what the emulated watch sent as evdev key events through
 * g2-ring-remote's real Router (watch profile) and FaceclawSender, paced by the guest's log
 * timestamps. Uses the over-the-air HID reports ("faceclaw-remote: hid report 2XX") when the run
 * has them (tools/hid_force.py), otherwise the key requests ("faceclaw-remote: key N").
 * Android key injections are recorded instead of executed.
 */
public final class PhoneSim {
    /** Linux key codes for the stock report-2 consumer bits 0..7 (hid-input.c mapping). */
    static final int[] BIT_TO_KEY = {114, 115, 113, 164, 165, 163, 0x195, 168};
    /** Report bits per remote key index (patch/hid.c key_bits): 8 keys, then the 4 swipe chords. */
    static final int[] KEY_MASK = {0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x42, 0x44, 0x50, 0x60};
    private static final Pattern KEY = Pattern.compile("^\\[(\\d+)\\].*faceclaw-remote: key (\\d+)$");
    private static final Pattern REPORT = Pattern.compile("^\\[(\\d+)\\].*faceclaw-remote: hid report 2([0-9a-f]{2})$");

    public static void main(String[] args) throws Exception {
        Config config = Config.load(new File(args[0]));
        config.port = Integer.parseInt(args[2]);
        config.tokenFile = args[3];
        File gestures = new File(args[4]);
        Config.Profile watch = config.profile("watch");
        FaceclawSender sender = new FaceclawSender(config);
        sender.start();
        Router router = new Router(config, sender, argv -> {
            synchronized (PhoneSim.class) {
                try (FileWriter w = new FileWriter(gestures, true)) {
                    w.write("{\"android\": \"" + String.join(" ", argv) + "\"}\n");
                }
            }
            return 0;
        });
        List<String> lines = Files.readAllLines(new File(args[1]).toPath(), StandardCharsets.ISO_8859_1);
        boolean overAir = lines.stream().anyMatch(l -> REPORT.matcher(l.trim()).find());
        List<long[]> presses = new ArrayList<>();
        for (String line : lines) {
            Matcher m = (overAir ? REPORT : KEY).matcher(line.trim());
            if (!m.find()) {
                continue;
            }
            int mask = overAir ? Integer.parseInt(m.group(2), 16) : KEY_MASK[Integer.parseInt(m.group(2))];
            if (mask != 0) {
                presses.add(new long[] {Long.parseLong(m.group(1)), mask});
            }
        }
        Log.i("replaying " + presses.size() + (overAir ? " over-the-air HID reports" : " key requests"));
        long start = System.currentTimeMillis();
        long first = presses.isEmpty() ? 0 : presses.get(0)[0];
        for (long[] p : presses) {
            long wait = start + (p[0] - first) - System.currentTimeMillis();
            if (wait > 0) {
                Thread.sleep(wait);
            }
            // Like hid-input: one EV_KEY per set bit in bit order, then SYN; same for the release.
            for (int value = 1; value >= 0; value--) {
                for (int bit = 0; bit < 8; bit++) {
                    if ((p[1] & (1 << bit)) != 0) {
                        int code = BIT_TO_KEY[bit];
                        if (value == 1) {
                            Log.i("watch HID bit " + bit + " -> " + KeyNames.name(code));
                        }
                        router.onEvent("watch", watch, TouchDecoder.EV_KEY, code, value, p[0]);
                    }
                }
                router.onEvent("watch", watch, TouchDecoder.EV_SYN, TouchDecoder.SYN_REPORT, 0, p[0]);
            }
        }
        Thread.sleep(1500);
        Log.i("sender: " + sender.stats());
    }
}

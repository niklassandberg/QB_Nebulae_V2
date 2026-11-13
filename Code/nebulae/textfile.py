# Text files a person can edit (USB stick, the web page, by hand) are UTF-8,
# with or without a BOM; \r\n and \r line ends read as \n, as in text mode.
# Any other encoding is not guessed: fatal.badFile() stops Nebulae.
import fatal

BOM = b"\xef\xbb\xbf"


def decode(data, path):
    skip = len(BOM) if data.startswith(BOM) else 0
    try:
        text = data[skip:].decode("utf-8")
    except UnicodeDecodeError as e:
        fatal.badFile(path, skip + e.start)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read(path):
    with open(path, "rb") as f:
        return decode(f.read(), path)


# As iterating a file in text mode: every line ends with "\n" but the last.
def lines(path):
    parts = read(path).split("\n")
    out = [p + "\n" for p in parts[:-1]]
    if parts[-1]:
        out.append(parts[-1])
    return out

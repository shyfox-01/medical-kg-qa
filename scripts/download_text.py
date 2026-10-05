import re
import urllib.request
import zipfile

from scripts.download_structured import RAW, download


def main() -> None:
    request = urllib.request.Request('https://medlineplus.gov/xml.html',
                                    headers={'User-Agent':'medkg-research/0.1'})
    with urllib.request.urlopen(request,timeout=30) as response:
        page = response.read().decode()
    urls = re.findall(r'href="([^"]*mplus_topics[^"\s]*\.xml)"',page)
    if not urls:
        raise RuntimeError('Latest MedlinePlus XML link not found')
    from urllib.parse import urljoin
    # The official page lists newest first; do not invent a date or download other datasets.
    print(download(urljoin('https://medlineplus.gov/xml.html',urls[0]),RAW/'medlineplus.xml'))
    print(download('https://ftp.ncbi.nlm.nih.gov/pub/lu/BioRED/BIORED.zip',RAW/'BIORED.zip'))
    directory = RAW/'biored'
    directory.mkdir(exist_ok=True)
    with zipfile.ZipFile(RAW/'BIORED.zip') as archive:
        for info in archive.infolist():
            target = (directory/info.filename).resolve()
            if not target.is_relative_to(directory.resolve()):
                raise ValueError('Unsafe archive path')
        archive.extractall(directory)
    print('Authorized text and BioRED files ready')


if __name__=='__main__':
    main()

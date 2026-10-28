from dataclasses import asdict, dataclass, field


@dataclass
class Listing:
    source: str
    source_id: str
    url: str
    title: str
    make: str
    model: str
    year: int | None
    trim: str = ""          # trim text as the seller wrote it
    site_trim: str = ""     # the site's own trim classification (CarGurus decodes it from the VIN)
    fuel: str = ""          # gas | hybrid | phev | electric | "" when the listing doesn't say
    price: int | None = None
    km: int | None = None
    city: str = ""
    province: str = ""
    postal: str = ""
    lat: float | None = None
    lon: float | None = None
    dealer: str = ""
    seller_type: str = ""   # dealer | private
    condition: str = ""     # used | new | demo
    vin: str = ""
    text: str = ""          # description, used only for matching and never stored
    features: list[str] = field(default_factory=list)
    target: str = ""
    confidence: str = ""    # confirmed | likely
    evidence: str = ""

    @property
    def key(self):
        return f"{self.source}:{self.source_id}"

    def record(self):
        data = asdict(self)
        del data["text"]
        return data


@dataclass
class SourceResult:
    listings: list[Listing]
    errors: list[str]
    requests: int

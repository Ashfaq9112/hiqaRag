countries = ["carlow", "cavan", "clare", "cork", "donegal", "dublin", "galway", "kerry", "kildare", "kilkenny",
"laois", "leitrim", "limerick", "longford", "louth", "mayo", "meath", "monaghan", "offaly",
"roscommon", "sligo", "tipperary", "waterford", "westmeath", "wexford", "wicklow"]




def extract_county(text:str) -> str | None:
    for piece in reversed(text.split(',')):  # last piece first, so a street called "Cork Road" can't win
        words = piece.lower().replace('.', ' ').split()  # "Co. Dublin" -> ["co", "dublin"]
        for county in countries:
            if county in words:  # whole word, not a substring
                return county.capitalize()
    return None



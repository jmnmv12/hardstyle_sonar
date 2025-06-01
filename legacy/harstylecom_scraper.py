from bs4 import BeautifulSoup
import requests
import time
from datetime import datetime, timedelta
from models import TrackData, Genre


class HardstyleDotComScavengerHardstyle:

    def _is_within_last_week(self, date_str):
        # Convert the date string to a datetime object
        date_obj = datetime.strptime(date_str, "%d.%m.%Y")

        # Get the current date
        current_date = datetime.now()

        # Calculate the date one week ago
        one_week_ago = current_date - timedelta(days=7)

        # Check if the date falls within the last week
        return date_obj > one_week_ago and date_obj <= current_date

    def _extract_artist(self, track):
        node_1 = track.find("span", class_="artists").find("a", class_="highlight")

        if node_1 is not None:
            return node_1.get("title")

        return track.find("span", class_="artists").text

    def _extract_tracks_out_of_list(self, album_tracks):
        track_data = []
        web = requests.Session()
        for track in album_tracks:
            track_object = TrackData()
            track_object.genre = Genre.Hardstyle

            track_node = track.find_all("a", class_="linkTitle")

            track_detail_url = track_node[0].get("href")
            response_track_detail = web.get(f"https://hardstyle.com{track_detail_url}")

            soup_track_detail = BeautifulSoup(
                response_track_detail.content, "html.parser"
            )

            release_date_str = soup_track_detail.find("span", class_="date").text

            if not self._is_within_last_week(release_date_str):
                continue

            title = track_node[0].get("title")
            mix_type = track_node[1].get("title")

            if "remix" not in mix_type.lower():
                mix_type = ""

            artist = self._extract_artist(track)

            track_object.title = f"{title} {mix_type}" if mix_type else title
            track_object.artist_name = artist

            track_data.append(track_object)

        return track_data

    def scavenge_for_tracks(self):
        track_data = []
        web = requests.Session()

        # Fetching albums
        """
        response_albums = web.get("https://hardstyle.com/en/albums")
        soup_albums = BeautifulSoup(response_albums.content, "html.parser")

        nodes2 = soup_albums.find_all("div", class_="track")

        max_amount_of_albums = 15
        curr_amount_of_albums = 0

        print("Fetching albums")
        # print(nodes2)

        for node in nodes2:
            # print(node)
            curr_amount_of_albums += 1
            if max_amount_of_albums == curr_amount_of_albums:
                break

            z = node.find("div", class_="trackPoster").find("a").get("href")
            response_album_detail = web.get(f"https://hardstyle.com{z}")
            soup_album_detail = BeautifulSoup(
                response_album_detail.content, "html.parser"
            )

            album_track_list = soup_album_detail.find("div", class_="tracks")
            album_tracks = album_track_list.find_all("div", class_="trackContent")

            tracks = self._extract_tracks_out_of_list(album_tracks)
            track_data.extend(tracks)
        """

        print("Fetching tracks")
        # Fetching tracks
        for i in range(1, 5):
            time.sleep(1)
            response = web.get(
                f"https://hardstyle.com/en/tracks?page={i}&genre=Hardstyle"
            )
            soup_track_list = BeautifulSoup(response.content, "html.parser")

            track_list = soup_track_list.find_all("div", class_="trackContent")
            tracks = self._extract_tracks_out_of_list(track_list)
            track_data.extend(tracks)

        # Removing duplicate tracks
        # return track_data
        track_data = list(set(track_data))

        print(f"retrieved a total of {len(track_data)} entries from hardstyle.com")

        return track_data

    def between(self, text, first_string, last_string):
        pos1 = text.find(first_string) + len(first_string)
        pos2 = text.find(last_string, pos1)
        final_string = text[pos1:pos2]
        return final_string


def __main__():
    scavenger = HardstyleDotComScavengerHardstyle()
    tracks = scavenger.scavenge_for_tracks()

    # 1. Validation
    print("Validating retrieved data")
    for track in tracks:
        print(track.title, track.artist_name)
        if not all([track.title.strip(), track.artist_name.strip()]):
            print(track.title, track.artist_name)
            print("Validation failed")
            break

    # print(tracks)

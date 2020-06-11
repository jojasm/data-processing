import pandas as pd
from datetime import datetime
import os
import glob
import zipfile
import subprocess
import json
import common
from gva_geodatenshop import credentials


# Returns value from geocat
def geocat_value(key):
    if str(key) != '':
        pathlist = key.split('.')
        tmp = metadata
        for x in pathlist:
            tmp = tmp[x]
        return tmp
    else:
        return ''


def geocat_try(geocat_path_list):
    for key in geocat_path_list:
        try:
            return geocat_value(key)
        except (KeyError, TypeError):
            # This key apparently is not present, try the next one in the list
            pass
    print('Error: None of the given keys exist in the source dict...')
    raise KeyError(';'.join(geocat_path_list))


def remove_empty_string_from_list(string_list):
    return list(filter(None, string_list))


datafilename = 'ogd_datensaetze.csv'
print('Reading data file form ' + os.path.join(credentials.path_orig, datafilename) + '...')
datafile = credentials.path_orig + datafilename
data = pd.read_csv(datafile, sep=';', na_filter=False, encoding='cp1252')

metadatafilename = 'Metadata.csv'
print('Reading data file form ' + metadatafilename + '...')
metadata = pd.read_csv(metadatafilename, sep=';', na_filter=False, encoding='cp1252')

# join data and metadata (if any)
joined_data = pd.merge(data, metadata, on='ordnerpfad', how='left')
joined_data.to_csv('_alldata.csv', index=False, sep=';')

metadata_for_ods = []

print('Iterating over datasets...')
for index, row in joined_data.iterrows():
    # Construct folder path
    # path = credentials.path_orig + joined_data.iloc[1]['ordnerpfad'].replace('\\', '/')
    path = credentials.path_orig + row['ordnerpfad'].replace('\\', '/')
    print('Checking ' + path + '...')

    # Exclude raster data for the moment - we don't have them yet
    if row['import'] is True and row['art'] == 'Vektor':  # and (str(row['ordnerpfad'])) in required_topics
        # Get files from folder
        files = os.listdir(path)

        # How many unique shp files are there?
        shpfiles = glob.glob(os.path.join(path, '*.shp'))
        print(str(len(shpfiles)) + ' shp files in ' + path)

        # Which shapes need to be imported to ods?
        shapes_to_load = remove_empty_string_from_list(row['shapes'].split(';'))

        # Iterate over shapefiles - we need the shp_number to map custom titles and descriptions to the correct shapefile
        for shp_number in range(0, len(shpfiles)):
            shpfile = shpfiles[shp_number]
            # Create zip file containing all necessary files for each Shape
            shppath, shpfilename = os.path.split(shpfile)
            shpfilename_noext, shpext = os.path.splitext(shpfilename)

            # Determine shp_to_load_number - the index of the current shape that should be loaded to ods
            if len(shapes_to_load) == 0:
                # Load all shapes - use index of current shape in list of all shapes in the current folder
                shp_to_load_number = shp_number
            elif shpfilename_noext in shapes_to_load:
                # Only load certain shapes - use index of shape given in column "shapes"
                shp_to_load_number = shapes_to_load.index(shpfilename_noext)

            # If "shapes" column is empty: load all shapes - otherwise only shapes listed in column "shapes"
            if len(shapes_to_load) == 0 or shpfilename_noext in shapes_to_load:
                print('Preparing shape ' + shpfilename_noext + '...')
                # create local subfolder mirroring mounted drive
                folder = shppath.replace(credentials.path_orig, '')
                folder_flat = folder.replace('/', '__'). replace('\\', '__')
                zipfilepath_relative = os.path.join('data', folder_flat + '__' + shpfilename_noext + '.zip')
                zipfilepath = os.path.join(os.getcwd(), zipfilepath_relative)
                print('Creating zip file ' + zipfilepath)
                # todo: uncomment to create zip files
                zipf = zipfile.ZipFile(zipfilepath, 'w')
                # zipf = zipfile.ZipFile(os.path.join(path, shpfilename_noext + '.zip'), 'w')
                print('Finding Files to add to zip')
                # Include all files with shpfile's name
                files_to_zip = glob.glob(os.path.join(path, shpfilename_noext + '.*'))
                for file_to_zip in files_to_zip:
                    # Do not add the zip file into the zip file...
                    if not file_to_zip.endswith('.zip'):
                        # todo: uncomment to create zip files
                        zipf.write(file_to_zip, os.path.split(file_to_zip)[1])
                        pass
                zipf.close()

                # Upload zip file to ftp server
                ftp_remote_dir = 'harvesters/GVA/data'
                # todo: uncomment to enable shp file uploading again
                common.upload_ftp(zipfilepath_relative, credentials.ftp_server, credentials.ftp_user, credentials.ftp_pass, ftp_remote_dir)

                # Load metadata from geocat.ch
                # See documentation at https://www.geocat.admin.ch/de/dokumentation/csw.html
                # For unknown reasons (probably proxy-related), requests always returns http error 404, so we have to revert to launching curl in a subprocess
                # curl -X GET "https://www.geocat.ch/geonetwork/srv/api/0.1/records/289b9c0c-a1bb-4ffc-ba09-c1e41dc7138a" -H "accept: application/json" -H "Accept: application/xml" -H "X-XSRF-TOKEN: a1284e46-b378-42a4-ac6a-d48069e05494"
                # resp = requests.get('https://www.geocat.ch/geonetwork/srv/api/0.1/records/2899c0c-a1bb-4ffc-ba09-c1e41dc7138a', params={'accept': 'application/json'}, proxies={'https': credentials.proxy})
                # resp = requests.get('https://www.geocat.ch/geonetwork/srv/api/0.1/records/2899c0c-a1bb-4ffc-ba09-c1e41dc7138a', headers={'accept': 'application/xml, application/json'}, proxies={'https': credentials.proxy})
                # cmd = 'curl -X GET "https://www.geocat.ch/geonetwork/srv/api/0.1/records/289b9c0c-a1bb-4ffc-ba09-c1e41dc7138a" -H "accept: application/json" -H "accept: application/json" -k'
                # args = shlex.split(cmd)

                # In some geocat URLs there's a tab character, remove it.
                geocat_uid = row['geocat'].rsplit('/', 1)[-1].replace('\t', '')
                metadata_file = 'metadata' + '/' + geocat_uid + '.json'
                cmd = '/usr/bin/curl --proxy ' + credentials.proxy + ' "https://www.geocat.ch/geonetwork/srv/api/0.1/records/' + geocat_uid + '" -H "accept: application/json" -s -k > ' + os.getcwd() + '/' + metadata_file
                print('Running curl to get geocat.ch metadata...')
                resp = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE)
                print('Processing geocat.ch metadata file ' + metadata_file + '...')
                with open(metadata_file, 'r', encoding='cp1252') as json_file:
                    print('Adding shape ' + shpfilename_noext + ' to harverster csv...')
                    json_string = json_file.read()
                    metadata = json.loads(json_string)

                    modified = datetime.strptime(str(row['dateaktualisierung']), '%Y%m%d').date().strftime("%Y-%m-%d")
                    schema_file = ''

                    # Get the correct title and ods_id from the list of titles in the title_nice column by checking th index of the current shpfile_noext in the shapes column
                    # Current shape explicitly set in column "shapes"
                    if shpfilename_noext in shapes_to_load:
                        title = str(row['titel_nice']).split(';')[shp_to_load_number]
                        ods_id = str(row['ods_id']).split(';')[shp_to_load_number]
                        if row['schema_file'] == 'True':
                            schema_file = ods_id + '.csv'
                    # Column "shapes" is empty, a title is set in column "title_nice", only one shape is present
                    elif len(shapes_to_load) == 0 and len(str(row['titel_nice'])) > 0 and len(shpfiles) == 1:
                        title = str(row['titel_nice'])
                        ods_id = str(row['ods_id'])
                        if row['schema_file'] == 'True':
                            schema_file = ods_id + '.csv'
                    # Multiple shape files present
                    elif len(shpfiles) > 1:
                        title = row['titel'].replace(':', ': ') + ': ' + shpfilename_noext
                    # 1 shape file present
                    else:
                        title = row['titel'].replace(':', ': ')
                        ods_id = row['ods_id']

                    # Geocat dataset descriptions are in lists if given in multiple languages. Let's assume that the German text is always the first element in the list.
                    geocat_description_textgroup = metadata['gmd:identificationInfo']['che:CHE_MD_DataIdentification']['gmd:abstract']['gmd:PT_FreeText']['gmd:textGroup']
                    geocat_description = geocat_description_textgroup[0]['gmd:LocalisedCharacterString']['#text'] if isinstance(geocat_description_textgroup, list) else geocat_description_textgroup['gmd:LocalisedCharacterString']['#text']
                    # Check if a description to the current shape is given in Metadata.csv
                    description_list = str(row['beschreibung']).split(';')
                    description = description_list[shp_to_load_number] if len(description_list) - 1 >= shp_to_load_number else ""

                    if str(row['dcat_ap_ch.domain']) != '':
                        dcat_ap_ch_domain = str(row['dcat_ap_ch.domain'])
                    else:
                        dcat_ap_ch_domain = 'geoinformation-kanton-basel-stadt'

                    # Add entry to harvester file
                    metadata_for_ods.append({
                        'ods_id': ods_id,
                        'name':  geocat_uid + ':' + shpfilename_noext,
                        'title': title,
                        'description': description if len(description) > 0 else geocat_description,
                        # Only add nonempty strings as references
                        'references': '; '.join(filter(None, [row['mapbs_link'], row['geocat'], row['referenz']])),  # str(row['mapbs_link']) + '; ' + str(row['geocat']) + '; ' + str(row['referenz']) + '; ',
                        'theme': str(row['theme']),
                        'keyword': str(row['keyword']),
                        'dcat_ap_ch.domain': dcat_ap_ch_domain,
                        'dcat_ap_ch.rights': 'NonCommercialAllowed-CommercialAllowed-ReferenceRequired',
                        'dcat.contact_name': 'Fachstelle für OGD Basel-Stadt',
                        'dcat.contact_email': 'opendata@bs.ch',
                        # 'dcat.contact_name': geocat_value(row['geocat_contact_firstname']) + ' ' + geocat_value(row['geocat_contact_lastname']),
                        # 'dcat.contact_name': geocat_try(['gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:pointOfContact.che:CHE_CI_ResponsibleParty.che:individualFirstName.gco:CharacterString.#text',
                        #                                  'gmd:distributionInfo.gmd:MD_Distribution.gmd:distributor.gmd:MD_Distributor.gmd:distributorContact.che:CHE_CI_ResponsibleParty.che:individualFirstName.gco:CharacterString.#text'])
                        #                      + ' '
                        #                      + geocat_try(['gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:pointOfContact.che:CHE_CI_ResponsibleParty.che:individualLastName.gco:CharacterString.#text',
                        #                                    'gmd:distributionInfo.gmd:MD_Distribution.gmd:distributor.gmd:MD_Distributor.gmd:distributorContact.che:CHE_CI_ResponsibleParty.che:individualLastName.gco:CharacterString.#text']),
                        # 'dcat.contact_email': geocat_value(row['geocat_email']),
                        # 'dcat.contact_email': geocat_try(['gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:pointOfContact.che:CHE_CI_ResponsibleParty.gmd:contactInfo.gmd:CI_Contact.gmd:address.che:CHE_CI_Address.gmd:electronicMailAddress.gco:CharacterString.#text',
                        #                                   'gmd:distributionInfo.gmd:MD_Distribution.gmd:distributor.gmd:MD_Distributor.gmd:distributorContact.che:CHE_CI_ResponsibleParty.gmd:contactInfo.gmd:CI_Contact.gmd:address.che:CHE_CI_Address.gmd:electronicMailAddress.gco:CharacterString.#text',
                        #                                   'gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:pointOfContact[0].che:CHE_CI_ResponsibleParty.gmd:contactInfo.gmd:CI_Contact.gmd:address.che:CHE_CI_Address.gmd:electronicMailAddress.gco:CharacterString.#text']),
                        # 'dcat.created': geocat_value('geocat_created'),
                        'dcat.created': geocat_try(['gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:citation.gmd:CI_Citation.gmd:date.gmd:CI_Date.gmd:date.gco:DateTime.#text',
                                                    'gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:citation.gmd:CI_Citation.gmd:date.gmd:CI_Date.gmd:date.gco:Date.#text']),
                        'dcat.creator': geocat_try(['gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:pointOfContact.che:CHE_CI_ResponsibleParty.che:individualFirstName.gco:CharacterString.#text',
                                                    'gmd:distributionInfo.gmd:MD_Distribution.gmd:distributor.gmd:MD_Distributor.gmd:distributorContact.che:CHE_CI_ResponsibleParty.che:individualFirstName.gco:CharacterString.#text']),
                        'dcat.accrualperiodicity': row['dcat.accrualperiodicity'],
                        # todo: Maintenance interval in geocat - create conversion table geocat -> ODS theme. Value in geocat: gmd:identificationInfo.che:CHE_MD_DataIdentification.gmd:resourceMaintenance.che:CHE_MD_MaintenanceInformation.gmd:maintenanceAndUpdateFrequency.gmd:MD_MaintenanceFrequencyCode.@codeListValue
                        # License has to be set manually for the moment, since we cannot choose one of the predefined ones through this harvester type
                        # 'license': 'https://creativecommons.org/licenses/by/3.0/ch/deed.de',
                        'attributions': 'Quelle: Geodaten Kanton Basel-Stadt',
                        # For some datasets, keyword is a list
                        # 'keyword': isinstance(metadata["gmd:identificationInfo"]["che:CHE_MD_DataIdentification"]["gmd:descriptiveKeywords"][0]["gmd:MD_Keywords"]["gmd:keyword"], list)
                        # if metadata["gmd:identificationInfo"]["che:CHE_MD_DataIdentification"]["gmd:descriptiveKeywords"][0]["gmd:MD_Keywords"]["gmd:keyword"][0]["gco:CharacterString"]["#text"]
                        # else metadata["gmd:identificationInfo"]["che:CHE_MD_DataIdentification"]["gmd:descriptiveKeywords"][0]["gmd:MD_Keywords"]["gmd:keyword"]["gco:CharacterString"]["#text"],
                        'publisher': row['kontakt_dienststelle'] if row['kontakt_dienststelle'] != "Zentrale Dienste" else "Erziehungsdepartement - Zentrale Dienste",
                        'dcat.issued': modified,
                        # todo: give time in UTC
                        'modified': modified,
                        'language': 'de',
                        'source_dataset': 'https://data-bs.ch/opendatasoft/harvesters/GVA/' + zipfilepath_relative,
                        'schema_file': schema_file
                    })
            else:
                print('No shapes to load in this topic.')

        # No shp file: find out filename
        if len(shpfiles) == 0:
            pass
            # Load metadata from geocat.ch
            # Add entry to harvester file
            # FTP upload file

# Save harvester file
if len(metadata_for_ods) > 0:
    ods_metadata = pd.DataFrame().append(metadata_for_ods, ignore_index=True, sort=False)
    ods_metadata_filename = 'Opendatasoft_Export_GVA.csv'
    ods_metadata.to_csv(ods_metadata_filename, index=False, sep=';')

    # FTP upload file
    print('Uploading ODS harvester file to FTP Server...')
    common.upload_ftp(ods_metadata_filename, credentials.ftp_server, credentials.ftp_user, credentials.ftp_pass, 'harvesters/GVA')

    # Upload each schema_file
    print('Uploading ODS schema files to FTP Server...')
    for schemafile in ods_metadata['schema_file'].unique():
        if schemafile != '':
            print('Uploading ODS schema files to FTP Server: ' + schemafile + '...')
            common.upload_ftp(schemafile, credentials.ftp_server, credentials.ftp_user, credentials.ftp_pass, 'harvesters/GVA')

else:
    print('Harvester File contains no entries, no upload necessary.')

# Todo: After harvester runs, change datasets title in order to have human readable title and number as id
# Because ods_id cannot be set via csv harvester, initially the title should be set to ods_id, then after harvester runs,
# ods title can be changed for those datasets where it is still equal to ods_id.

print('Job successful.')




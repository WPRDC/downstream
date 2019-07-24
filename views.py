import os, requests, csv, ckanapi, time
from django.http import StreamingHttpResponse, HttpResponse
from django.shortcuts import redirect

from .ckan_util import get_resource_parameter, get_resource_name, get_package_title, get_row_and_column_counts

from pprint import pprint
try:
    from icecream import ic
except ImportError:  # Graceful fallback if IceCream isn't installed.
    ic = lambda *a: None if not a else (a[0] if len(a) == 1 else a)  # noqa

DEFAULT_SITE = "https://data.wprdc.org"

def eliminate_field(schema,field_to_omit):
    new_schema = []
    for s in schema:
        if s['id'] != field_to_omit:
            new_schema.append(s)
    return new_schema

# StreamingHttpResponse requires a File-like class that has a 'write' method
class Echo(object):
    def write(self, value):
        return value

def generate_header(ordered_fields, file_format):
    if file_format == 'csv':
        return ','.join(ordered_fields) + '\n'
    if file_format == 'tsv':
        return '\t'.join(ordered_fields) + '\n'

def write_to_excel_format(ckan, resource_id, chunk_size):
    records_format = 'objects'
    r = ckan.action.datastore_search(id=resource_id, limit=chunk_size, offset=0, records_format=records_format) #, filters={field: search_term})
    schema = eliminate_field(r['fields'],'_full_text') # Exclude _full_text from the schema.
    ordered_fields = [f['id'] for f in schema]
    data_rows = r['records']

    from pytablewriter import ExcelXlsxTableWriter
    writer = ExcelXlsxTableWriter()
    package_name = get_package_title(DEFAULT_SITE, resource_id)
    resource_name = get_resource_name(DEFAULT_SITE, resource_id)
    writer.table_name = "{}|{}".format(package_name, resource_name) # Excel sheet names will not show these characters: /\*[]:?
    # Also note that Excel sheet names get truncated to the first 31 characters.
    writer.headers = ordered_fields
    value_matrix = []
    for row in data_rows:
        new_row = [row[field] for field in ordered_fields]
        value_matrix.append(new_row)
    writer.value_matrix = value_matrix
    #writer.value_matrix = [
    #    [0,   0.1,      "hoge", True,   0,      "2017-01-01 03:04:05+0900"],
    #    [2,   "-2.23",  "foo",  False,  None,   "2017-12-23 12:34:51+0900"],
    #    [3,   0,        "bar",  "true",  "inf", "2017-03-03 22:44:55+0900"],
    #    [-10, -9.9,     "",     "FALSE", "nan", "2017-01-01 00:00:00+0900"],
    #]
    local_filename = "{}.xlsx".format(resource_id)
    writer.dump(local_filename)
    print("Wrote data to local Excel file")

    with open(local_filename, 'rb') as fp:
        data = fp.read()
    #filename = 'some-filename.xlsx'
    #response = HttpResponse(mimetype="application/ms-excel")
    #response['Content-Disposition'] = 'attachment; filename=%s' % filename # force browser to download file
    #response.write(data)
    if os.path.exists(local_filename):
        os.remove(local_filename)
        # [ ] Probably there's a better way than saving the file, then reading the data, and deleting the file.

        # * Specifically pytablewriter's Excel table writer has a write_table_iter() function explicitly
        # for handling large files in steps:
        # https://pytablewriter.readthedocs.io/en/latest/pages/reference/writer.html#pytablewriter.ExcelXlsxTableWriter.write_table_iter
        # This could probably be used to convert this write_to_excel_format function into a generator
        # just by incrementing offset and sending the data in chunks. (How it handles the header/footer
        # of the XLSX files is completely unclear.)
    return data

def get_and_write_next_rows(pseudo_buffer, ckan, resource_id, start_line=0, file_format='csv'):
    offset = start_line
    chunk_size = 200000 # Maybe consider changing chunk_size dynamically based on current system resources.
    records_format = 'objects' if file_format == 'json' else file_format
    r = ckan.action.datastore_search(id=resource_id, limit=chunk_size, offset=offset, records_format=records_format) #, filters={field: search_term})
    schema = eliminate_field(r['fields'],'_full_text') # Exclude _full_text from the schema.
    ordered_fields = [f['id'] for f in schema]
    yield pseudo_buffer.write(generate_header(ordered_fields, file_format))
    while True:
        if offset != 0:
            r = ckan.action.datastore_search(id=resource_id, limit=chunk_size, offset=offset, records_format=records_format) #, filters={field: search_term})
        data = r['records'] # For records_format == 'csv', this is lines of CSV, which can be written directly.
        # When the end of the dataset has been reached, using the
        # "break" command is one way to halt further iteration.
        if len(data) == 0:
            break

        to_write = data
        yield pseudo_buffer.write(to_write)
        offset += chunk_size
        time.sleep(0.3)

def stream_response(request, resource_id, file_format='csv'):
    # NOTE: No Content-Length header!
    # Python documentation: "StreamingHttpResponse should only be used in
    # situations where it is absolutely required that the whole content
    # isn't iterated before transferring the data to the client. Because
    # the content can’t be accessed, many middlewares can't function
    # normally. For example the ETag and Content-Length headers can't
    # be generated for streaming responses."

    file_format = file_format.lower()
    ckan = ckanapi.RemoteCKAN(DEFAULT_SITE)
    resource_format = get_resource_parameter(DEFAULT_SITE, resource_id, parameter='format', API_key=None).lower()
    n = len(file_format)
    if resource_format == file_format:
        resource = ckan.action.resource_show(site=DEFAULT_SITE, id=resource_id)
        if 'url' in resource and resource['url'][-n:] == file_format:
        # If the source file is already in file_format, just serve the file directly.
            return redirect(resource['url'])

    if file_format in ['csv', 'tsv']:
        content_type = 'text/{}'.format(file_format)
    if file_format in ['json']:
        content_type = 'application/json'
        raise ValueError("JSON is not yet supported.")
    elif file_format in ['xlsx']:
        content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

        excel_row_limit = 100000
        row_count, col_count = get_row_and_column_counts(ckan, resource_id)
        if row_count > excel_row_limit:
            return HttpResponse("Excel files are not supported for row counts greater than {}.".format(excel_row_limit))
        excel_cell_limit = 200000 # Saving to a local file (which seems to be where it otherwise
        # gets stuck), downstream can handle a 1191 x 17 file (20247 cells), a 6828 x 9 file
        # (61452 cells), a 6404 x 19 file (121676 cells), and 27018 x 7 file (189126 cells), but
        # gets stuck on a 1049 x 382 file (400718 cells).

        if row_count * col_count > excel_cell_limit:
            return HttpResponse("Excel files are not supported for cell counts greater than {}, and this table has {} cells.".format(excel_cell_limit, row_count*col_count))
        else:
            response = HttpResponse(content_type=content_type)
            filename = "{}.xlsx".format(resource_id)
            response['Content-Disposition'] = 'attachment; filename="{}"'.format(filename)
            response.write(write_to_excel_format(ckan, resource_id, excel_row_limit))
            return response
    else:
        response = StreamingHttpResponse(
                streaming_content=(get_and_write_next_rows(Echo(), ckan, resource_id, 0, file_format)),
            content_type=content_type,
        )
        # streaming_content: An iterator of strings representing the content.

    response['Content-Disposition'] = 'attachment;filename={}.{}'.format(resource_id, file_format)
    return response

def index(request):
    page = """<span><big>Downstream: Helping you get more of that tasty WPRDC data</big></span><br><br>

        Downstream is capable of streaming tabular data from <a href="https://data.wprdc.org/">https://data.wprdc.org</a> so you can download it.<br>
        <br>
        <b>When is this useful?</b><br>
        1) Sometimes the data table is too big, and CKAN can't generate the CSV output for you. In this case, try Downstream!<br>
        2) Maybe you want that tabular data in some other format like TSV or Excel* (XSLX).<br>
        <br>
        <b>OK, how do I do it?</b><br>
        Just enter a URL like this in your browser:<br>
        &nbsp;&nbsp;&nbsp;&nbsp;https://tools.wprdc.org/downstream/&lt;CKAN resource ID&gt;<br>
        <br>
        You can find the CKAN resource ID at the end of the URL for the data table you want. For instance, the data table for the locations of Carnegie Library of Pittsburgh libraries can be found at
        &nbsp;&nbsp;&nbsp;&nbsp;<a href="https://data.wprdc.org/dataset/libraries/resource/14babf3f-4932-4828-8b49-3c9a03bae6d0">https://data.wprdc.org/dataset/libraries/resource/14babf3f-4932-4828-8b49-3c9a03bae6d0</a><br>
        Just grab that long string at the end of the URL and insert it after "downstream/", yielding a URL like this:<br>
        &nbsp;&nbsp;&nbsp;&nbsp;<a href="https://tools.wprdc.org/downstream/14babf3f-4932-4828-8b49-3c9a03bae6d0">https://tools.wprdc.org/downstream/14babf3f-4932-4828-8b49-3c9a03bae6d0</a><br>
        <br>
        A CSV version of that data table will start downloading to your browser. (The default format is CSV.)<br>
        <br>
        You can also download other formats by modifying the URL:<br>
        TSV:&nbsp;&nbsp;<a href="https://tools.wprdc.org/downstream/14babf3f-4932-4828-8b49-3c9a03bae6d0/tsv">https://tools.wprdc.org/downstream/14babf3f-4932-4828-8b49-3c9a03bae6d0/tsv</a><br>
        Excel:&nbsp;&nbsp;<a href="https://tools.wprdc.org/downstream/14babf3f-4932-4828-8b49-3c9a03bae6d0/xlsx">https://tools.wprdc.org/downstream/14babf3f-4932-4828-8b49-3c9a03bae6d0/xlsx</a><br>

        <br>
        <br>
        <small>* Conversions of data to Excel format are currently limited to medium-sized tables (less than 100,000 rows and less than 200,000 cells).</small>
        <br>
        <br>

        """
    return HttpResponse(page)

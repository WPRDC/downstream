import requests, csv, ckanapi, time
from django.http import StreamingHttpResponse

DEFAULT_SITE = "https://data.wprdc.org"

def eliminate_field(schema,field_to_omit):
    new_schema = []
    for s in schema:
        if s['id'] != field_to_omit:
            new_schema.append(s)
    return new_schema

def total_rows(ckan,query):
    row_counting_query = 'SELECT COUNT(*) FROM ({}) subresult'.format(query)
    r = ckan.action.datastore_search_sql(sql=row_counting_query)
    count = int(r['records'][0]['count'])
    return count

# StreamingHttpResponse requires a File-like class that has a 'write' method
class Echo(object):
    def write(self, value):
        return value

def generate_header(ordered_fields, file_format):
    if file_format == 'csv':
        return ','.join(ordered_fields) + '\n'
    if file_format == 'tsv':
        return '\t'.join(ordered_fields) + '\n'

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
    if file_format in ['csv', 'tsv']:
        content_type = 'text/{}'.format(file_format)
    ckan = ckanapi.RemoteCKAN(DEFAULT_SITE)
    response = StreamingHttpResponse(
            streaming_content=(get_and_write_next_rows(Echo(), ckan, resource_id, 0, file_format)),
        content_type=content_type,
    )
    # streaming_content: An iterator of strings representing the content.

    response['Content-Disposition'] = 'attachment;filename={}.{}'.format(resource_id, file_format)
    return response

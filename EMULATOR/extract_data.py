
# eeg_data_chXX = {eeg_out[63:40],impedance_out_i[39:24],impedance_out_q[23:8], edo_out[7:0]};
# EEG_NEURAL_DATA_WIDTH = 24;
# EEG_IMPEDANCE_DATA_WIDTH = 16;
# EEG_EDO_DATA_WIDTH = 8;
#
# eeg_packet <= {eeg_packet_msb,eeg_packet_id[6:0],
#               eeg_data_channel_7,eeg_data_channel_6,eeg_data_channel_5,
#               eeg_data_channel_4,eeg_data_channel_3,eeg_data_channel_2,
#               eeg_data_channel_1,eeg_data_channel_0};

import numpy



def extract_from_raw_line(raw_data):
    # event       = raw_data[0]
    raw_data = raw_data.strip("\n")
    raw_data = raw_data.strip("\r")
    # print(len(raw_data))
    if (len(raw_data) == 136):
        packet_id = raw_data[0:1]
        ch7_data = raw_data[2:17]
        ch6_data = raw_data[18:33]
        ch5_data = raw_data[34:49]
        ch4_data = raw_data[50:65]
        ch3_data = raw_data[66:81]
        ch2_data = raw_data[82:97]
        ch1_data = raw_data[98:113]
        ch0_data = raw_data[114:130]
        raw_ch = numpy.array([ch0_data, ch1_data, ch2_data, ch3_data, ch4_data, ch5_data, ch6_data, ch7_data])

        data_array = []
        data_array.append(int(packet_id, 16))

        for i in range(8):
            data_array.append(int(raw_ch[i][0:1], 16))  # ch_edo
            data_array.append(int(raw_ch[i][2:5], 16))  # ch_q
            data_array.append(int(raw_ch[i][6:9], 16))  # ch_i
            data_array.append(int(raw_ch[i][10:15], 16))  # ch_eeg
        data_string = ','.join(map(str, data_array))  # collapse array into comma delimited string
        return data_string
    else:
        return raw_data

